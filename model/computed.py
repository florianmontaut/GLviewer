# model/computed.py
"""
Voie calculée : voie d'un fichier dont les valeurs sont données par une formule sur les
autres voies, par ex. les pertes évacuées par l'eau
    [Débit]/60*4180*([T eau sortie]-[T eau entrée])
ou une fonction du temps
    100*sin(2*pi*50*time)

Elle se comporte comme une voie mesurée (filtres, analyses, vue « Par voie », Benchmark) :
seules ses données brutes sont calculées au lieu d'être lues dans le fichier.

Base de temps : échantillons du fichier hôte (temps affiché : décalage et troncature
compris), ou une période propre (fonction du temps plus rapide que l'échantillonnage).
Une voie d'un autre fichier, ou d'une autre base de temps, est interpolée (nan hors de
la zone commune). Les voies utilisées sont prises après leurs filtres.

Désignation des voies :
    [T AMB]         voie du fichier hôte, par son nom (espaces, accents admis)
    [200 W:T AMB]   voie d'un autre fichier, désigné par son étiquette ou son nom
    CH3             voie du fichier hôte par son numéro (GL) ou par un nom sans espace
    time            temps (s)

Tables de correspondance (model.formula.lut) : steps(time; 0; 200; 201; 800) donne une
puissance par paliers, interp([V]; 0; -40; 5; 150) une courbe d'étalonnage.
"""
import numpy as np

from model.base_objects import SignalObject
from model.channels import channel_key
from model.formula import FormulaError, evaluate, parse, references
from ressources import custom_struct_functions

HOST_TIME_BASE = "Host file"
OWN_TIME_BASE = "Own period"
TIME = "time"
# garde-fou d'une période propre trop fine sur un long enregistrement
MAX_POINTS = 5_000_000

# voies calculées en cours de calcul : détection des références circulaires
_computing = []


class ComputedSignal(SignalObject):

    is_computed = True

    PARAMETER_SCHEMA = {
        'Curve name':   {
                            'type': 'str',
                            'default': "Formula",
                            "key": "name",
                        },
        'Formula':      {
                            'type': 'str',
                            'default': "",
                            "key": "formula",
                            "description": "Voies entre crochets : [T AMB], [200 W:T AMB] "
                                            "(autre fichier) ; time : temps (s) ; fonctions "
                                            "sin, cos, exp, log, sqrt, abs, max, min, avg... ;"
                                            " tables : steps(time; 0; 200; 201; 800) "
                                            "(paliers), interp(x; x1; y1; x2; y2...) ;"
                                            " arguments séparés par ;",
                        },
        'Curve unit':   {
                            'type': 'str',
                            'default': "",
                            "key": "unit",
                        },
        'Time base':    {
                            'type': 'list',
                            'default': HOST_TIME_BASE,
                            'limits': [HOST_TIME_BASE, OWN_TIME_BASE],
                            "key": "time_base",
                        },
        'Own period (s)': {
                            'type': 'float',
                            'default': 0.001,
                            'limits': (1e-9, None),
                            'suffix': 's',
                            "key": "period",
                        },
        'Curve pen':    {
                            'type': 'pen',
                            'expanded': True,
                            "key": "pen",
                        },
    }
    # paramètres de la formule (les autres : affichage)
    FORMULA_KEYS = ("name", "formula", "unit", "time_base", "period")

    def __init__(self, file_obj, name: str, formula: str, unit: str = "",
                 time_base: str = HOST_TIME_BASE, period: float = 0.001, pen=None,
                 replaces=None):
        """replaces : voie calculée dont celle-ci est l'essai de modification (même nom admis)"""
        super().__init__(file_obj, name, pen or file_obj.getDefaultPen())
        self.unit = unit
        self.time_base = time_base
        self.period = period
        self.formula = formula
        self.error = None            # échec du dernier calcul (voie introuvable...)
        self.warnings = []           # voies interpolées plus lentes que la base de temps
        self._replaces = replaces
        self._base = None            # (x, y) calculés par la formule
        self._base_key = None
        self.validate(self.formula_params())

    # ---------------- paramètres ----------------

    def formula_params(self) -> dict:
        return {key: getattr(self, key) for key in self.FORMULA_KEYS}

    def validate(self, params: dict):
        """Paramètres de formule cohérents (FormulaError / ValueError sinon)."""
        self._tree = parse(params["formula"])
        if not params["name"].strip():
            raise FormulaError("The channel name is empty")
        others = {s.name for s in self.file.signals
                  if s is not self and s is not getattr(self, "_replaces", None)}
        if params["name"] in others:
            raise FormulaError(f"A channel named '{params['name']}' already exists in "
                               f"{self.file.label or self.file.name}")
        if params["time_base"] not in (HOST_TIME_BASE, OWN_TIME_BASE):
            raise ValueError(f"Unknown time base: {params['time_base']}")
        if not params["period"] > 0:
            raise ValueError("The own period must be > 0")

    def set_params(self, newParams):
        formula = {k: v for k, v in newParams.items() if k in self.FORMULA_KEYS}
        if formula:
            self.validate({**self.formula_params(), **formula})
        super().set_params(newParams)
        self._base_key = None        # recalcul au prochain accès
        self.invalidate()

    @property
    def display_name(self):
        return f"ƒ {self.name}" + (" *" if self.is_modified else "")

    # ---------------- voies utilisées ----------------

    def _files(self):
        workspace = getattr(self.file, "workspace", None)
        return list(workspace.files) if workspace is not None else [self.file]

    def _find(self, ref: str, bracket: bool):
        """Voie désignée par ref ([nom], [fichier:nom] ou identifiant CH3)."""
        file_obj, name = self.file, ref
        if bracket and ":" in ref:
            prefix, name = (part.strip() for part in ref.split(":", 1))
            files = self._files()
            file_obj = next((f for f in files if prefix.casefold() in
                             {(f.label or "").casefold(), f.name.casefold()}), None)
            if file_obj is None:
                names = ", ".join(f.label or f.name for f in files)
                raise FormulaError(f"Unknown file '{prefix}' in [{ref}] (files: {names})")
        signals = file_obj.signals
        found = (next((s for s in signals if s.name == name), None)
                 or next((s for s in signals if channel_key(s.name) == channel_key(name)), None)
                 or next((s for s in signals if s.channel_id
                          and s.channel_id.casefold() == name.casefold()), None))
        if found is None:
            label = f"[{ref}]" if bracket else ref
            raise FormulaError(f"Unknown channel {label} in {file_obj.label or file_obj.name} "
                               f"(channels: {', '.join(s.name for s in signals)})")
        if found is self:
            raise FormulaError(f"The formula of '{self.name}' uses the channel itself")
        if found.file.removed:
            raise FormulaError(f"The file of [{ref}] ({found.file.name}) has been removed")
        return found

    def inputs(self) -> dict:
        """{clé de la formule : voie} ; clé « [nom] » ou identifiant (CH3)."""
        names, channels = references(self._tree)
        found = {name: self._find(name, False) for name in names if name != TIME}
        found.update({f"[{ref}]": self._find(ref, True) for ref in channels})
        return found

    def depends_on(self, sig, _seen=None) -> bool:
        """La formule utilise-t-elle sig, directement ou via d'autres voies calculées ?"""
        _seen = _seen if _seen is not None else set()
        try:
            inputs = list(self.inputs().values())
        except FormulaError:
            return False
        for other in inputs:
            if other is sig:
                return True
            if isinstance(other, ComputedSignal) and other not in _seen:
                _seen.add(other)
                if other.depends_on(sig, _seen):
                    return True
        return False

    def _source_key(self) -> tuple:
        """État de tout ce dont dépend la formule : un changement impose un recalcul."""
        files = tuple((f.id, f.removed) for f in self._files())
        if self in _computing:
            return ("cycle",)
        _computing.append(self)
        try:
            refs = tuple(sorted((key, sig.input_key()) for key, sig in self.inputs().items()))
        except FormulaError as e:
            refs = ("error", str(e))
        finally:
            _computing.remove(self)
        return (tuple(self.formula_params().items()), self.file.time_key(), files, refs)

    def input_key(self) -> tuple:
        return (self.pipeline_version, self._source_key())

    # ---------------- calcul ----------------

    def host_time_base(self) -> np.ndarray:
        x = np.asarray(self.file.get_x(), dtype=float)
        if self.time_base == HOST_TIME_BASE or len(x) == 0:
            return x
        points = (x[-1] - x[0]) / self.period
        if points > MAX_POINTS:
            raise FormulaError(f"Own period too small: {points:,.0f} points (max "
                               f"{MAX_POINTS:,}) ; increase the period or truncate the file")
        return np.arange(x[0], x[-1] + self.period / 2, self.period)

    @staticmethod
    def _on_time_base(sig, x, warnings):
        sx = np.asarray(sig.x, dtype=float)
        sy = np.asarray(sig.y, dtype=float)
        if sx.shape == x.shape and np.array_equal(sx, x):
            return sy
        if len(sx) > 1 and len(x) > 1 and np.median(np.diff(sx)) > 1.5 * np.median(np.diff(x)):
            warnings.append(f"{sig.name} ({sig.file.label or sig.file.name}) : échantillonnage "
                            f"plus lent que la base de temps, valeurs interpolées")
        # nan hors de la zone commune : pas d'extrapolation
        return np.interp(x, sx, sy, left=np.nan, right=np.nan)

    def evaluate(self) -> tuple[np.ndarray, np.ndarray, list]:
        """(x, y, avertissements) de la formule ; FormulaError si elle ne peut être calculée."""
        if self in _computing:
            chain = " -> ".join(s.name for s in _computing[_computing.index(self):])
            raise FormulaError(f"Circular reference: {chain} -> {self.name}")
        _computing.append(self)
        try:
            x = self.host_time_base()
            warnings = []
            variables = {key: self._on_time_base(sig, x, warnings)
                         for key, sig in self.inputs().items()}
            variables[TIME] = x
            value = evaluate(self._tree, variables)
        finally:
            _computing.remove(self)
        y = np.full(x.shape, float(value)) if np.ndim(value) == 0 else np.asarray(value, float)
        if y.shape != x.shape:
            raise FormulaError(f"The formula gives {y.size} values for {x.size} time samples")
        return x, y, warnings

    def base(self) -> tuple[np.ndarray, np.ndarray]:
        """
        Données brutes de la voie (avant ses filtres), recalculées quand une donnée
        d'entrée change. En cas d'échec : valeurs nan et raison dans self.error.
        """
        key = self._source_key()
        if self._base is None or key != self._base_key:
            try:
                x, y, self.warnings = self.evaluate()
                self.error = None
            except FormulaError as e:
                x = np.asarray(self.file.get_x(), dtype=float)
                y = np.full(x.shape, np.nan)
                self.warnings, self.error = [], str(e)
            x.setflags(write=False)
            self._base, self._base_key = (x, y), key
        return self._base

    @property
    def x(self):
        if not self.pipeline:
            return self.base()[0]
        self.compute()
        return self._x_cache

    @property
    def raw_x(self):
        return self.base()[0]

    @property
    def raw_y(self):
        return self.base()[1].copy()

    def compute(self):
        base = self.base()
        raw_x, raw_y = base
        # cache lié au résultat de la formule (même axe des temps, valeurs recalculées)
        if (self._cache_valid and self._cache_version == self.pipeline_version
                and self._cache_raw_x is base):
            return self._cache
        x, y = raw_x, raw_y.copy()
        for node in self.pipeline.values():
            y = node.apply(x, y)
            x = node.apply_x(x)
        if x.flags.writeable:
            x.setflags(write=False)
        self._cache, self._x_cache, self._cache_raw_x = y, x, base
        self._cache_valid, self._cache_version = True, self.pipeline_version
        return y

    # ---------------- sauvegarde ----------------

    def to_dict(self):
        data = super().to_dict()
        data["computed"] = {k: v for k, v in self.formula_params().items() if k != "name"}
        return data

    @staticmethod
    def from_saved(file_obj, data, filter_factory, analysis_factory):
        """Voie calculée relue dans un projet (voir SignalObject.from_dict)."""
        computed = data["computed"]
        sig = ComputedSignal(file_obj, data["name"], computed["formula"],
                             unit=computed.get("unit", ""),
                             time_base=computed.get("time_base", HOST_TIME_BASE),
                             period=computed.get("period", 0.001))
        SignalObject._restore_nodes(sig, data, filter_factory, analysis_factory)
        return sig

    @staticmethod
    def from_formula_analysis(file_obj, params):
        """Formule en analyse (projets de la version précédente) -> voie calculée."""
        name, n = params.get("name") or "Formula", 2
        while name in {s.name for s in file_obj.signals}:
            name, n = f"{params.get('name') or 'Formula'} ({n})", n + 1
        return ComputedSignal(file_obj, name, params["formula"], unit=params.get("unit", ""),
                              time_base=params.get("time_base", HOST_TIME_BASE),
                              period=params.get("period", 0.001))
