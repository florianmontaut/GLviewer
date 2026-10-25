# model/analysis/formula.py
"""
Analyse « Formula » : nouvelle courbe calculée par une formule sur les voies, par ex.
les pertes évacuées par l'eau  [Débit]/60*4180*([T eau sortie]-[T eau entrée])
ou une fonction du temps        100*sin(2*pi*50*time)

Base de temps : celle de la voie sur laquelle la formule est créée (fichier hôte, temps
affiché : décalage et troncature compris), ou une période propre (fonctions du temps).
Une voie d'un autre fichier, ou décalée en temps, est interpolée sur cette base de temps
(nan hors de la zone commune).

Désignation des voies :
    [T AMB]         voie du fichier hôte, par son nom (espaces, accents admis)
    [200 W:T AMB]   voie d'un autre fichier, désigné par son étiquette ou son nom
    CH3             voie du fichier hôte par son numéro (GL) ou par un nom sans espace
    time            temps (s)
"""
import numpy as np
import pyqtgraph as pg

from .base_analysis import AnalysisNode
from ..base_objects import DerivedSignalObject
from ..channels import channel_key
from ..formula import FormulaError, evaluate, parse, references
from ressources import custom_types

HOST_TIME_BASE = "Host file"
OWN_TIME_BASE = "Own period"
TIME = "time"


class FormulaAnalysis(AnalysisNode):

    action_type = custom_types.qSignalType.FORMULA
    # garde-fou d'une période propre trop fine sur un long enregistrement
    MAX_POINTS = 5_000_000

    PARAMETER_SCHEMA = {
        "Formula": {
                        "type": "str",
                        "default": "",
                        "key": "formula",
                        "description": "Voies entre crochets : [T AMB], [200 W:T AMB] (autre "
                                        "fichier) ; time : temps (s) ; fonctions sin, cos, "
                                        "exp, log, sqrt, abs, max, min, avg... ; "
                                        "arguments séparés par ;",
                    },
        "Name": {
                        "type": "str",
                        "default": "Formula",
                        "key": "name",
                    },
        "Unit": {
                        "type": "str",
                        "default": "",
                        "key": "unit",
                    },
        "Time base": {
                        "type": "list",
                        "default": HOST_TIME_BASE,
                        "limits": [HOST_TIME_BASE, OWN_TIME_BASE],
                        "key": "time_base",
                        "description": "Échantillons du fichier hôte, ou période propre "
                                        "(fonction du temps plus rapide que l'échantillonnage)",
                    },
        "Own period (s)": {
                        "type": "float",
                        "default": 0.001,
                        "limits": (1e-9, None),
                        "suffix": "s",
                        "key": "period",
                    },
    }

    # ---------------- paramètres ----------------

    def validate(self, params):
        self._tree = parse(params["formula"])          # FormulaError : syntaxe invalide
        if params["time_base"] not in (HOST_TIME_BASE, OWN_TIME_BASE):
            raise ValueError(f"Unknown time base: {params['time_base']}")
        if not params["period"] > 0:
            raise ValueError("The own period must be > 0")

    @property
    def display_name(self) -> str:
        return f"{self.get_param('name')} = {self.get_param('formula')}"

    # ---------------- voies utilisées ----------------

    @staticmethod
    def _files(parent_signal):
        workspace = getattr(parent_signal.file, "workspace", None)
        return list(workspace.files) if workspace is not None else [parent_signal.file]

    def _find(self, parent_signal, ref: str, bracket: bool):
        """Voie désignée par ref ([nom], [fichier:nom] ou identifiant CH3)."""
        file_obj, name = parent_signal.file, ref
        if bracket and ":" in ref:
            prefix, name = (part.strip() for part in ref.split(":", 1))
            files = self._files(parent_signal)
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
        if found.file.removed:
            raise FormulaError(f"The file of [{ref}] ({found.file.name}) has been removed")
        return found

    def inputs(self, parent_signal) -> dict:
        """{clé de la formule : SignalObject} ; clé « [nom] » ou identifiant (CH3)."""
        names, channels = references(self._tree)
        found = {name: self._find(parent_signal, name, False) for name in names if name != TIME}
        found.update({f"[{ref}]": self._find(parent_signal, ref, True) for ref in channels})
        return found

    def input_key(self, parent_signal) -> tuple:
        # périmée quand une voie utilisée change (filtre, décalage...) ou quand un fichier
        # est retiré / remis (voie introuvable puis retrouvée)
        files = tuple((f.id, f.removed) for f in self._files(parent_signal))
        try:
            refs = tuple(sorted((key, sig.input_key()) for key, sig in
                                self.inputs(parent_signal).items()))
        except FormulaError:
            refs = None
        return (parent_signal.input_key(), files, refs)

    # ---------------- calcul ----------------

    def time_base(self, parent_signal) -> np.ndarray:
        x = np.asarray(parent_signal.x, dtype=float)
        if self.get_param("time_base") == HOST_TIME_BASE:
            return x
        period = self.get_param("period")
        points = (x[-1] - x[0]) / period
        if points > self.MAX_POINTS:
            raise FormulaError(f"Own period too small: {points:,.0f} points (max "
                               f"{self.MAX_POINTS:,}) ; increase the period or truncate the file")
        return np.arange(x[0], x[-1] + period / 2, period)

    @staticmethod
    def _on_time_base(sig, x, warnings):
        sx = np.asarray(sig.x, dtype=float)
        if sx.shape == x.shape and np.array_equal(sx, x):
            return np.asarray(sig.y, dtype=float)
        if len(sx) > 1 and len(x) > 1 and np.median(np.diff(sx)) > 1.5 * np.median(np.diff(x)):
            warnings.append(f"{sig.name} ({sig.file.label or sig.file.name}) : échantillonnage "
                            f"plus lent que la base de temps, valeurs interpolées")
        # nan hors de la zone commune : pas d'extrapolation
        return np.interp(x, sx, np.asarray(sig.y, dtype=float), left=np.nan, right=np.nan)

    def compute(self, parent_signal) -> DerivedSignalObject:
        x = self.time_base(parent_signal)
        warnings = []
        variables = {key: self._on_time_base(sig, x, warnings)
                     for key, sig in self.inputs(parent_signal).items()}
        variables[TIME] = x
        value = evaluate(self._tree, variables)
        y = np.full(x.shape, float(value)) if np.ndim(value) == 0 else np.asarray(value, float)
        if y.shape != x.shape:
            raise FormulaError(f"The formula gives {y.size} values for {x.size} time samples")

        derived = DerivedSignalObject(
                    parent_signal=parent_signal,
                    name=self.get_param("name"),
                    x=x,
                    y=y,
                    pen=pg.mkPen("m", width=2),
                    metadata={
                        "type": "formula",
                        "formula": self.get_param("formula"),
                        "warnings": warnings,
                        "analysis_id": self.id,
                    },
                )
        derived.unit = self.get_param("unit")
        return derived
