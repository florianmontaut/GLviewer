
import uuid
import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import Qt
from scipy.optimize import curve_fit

from ressources import custom_items
from ressources.custom_exceptions import InvalidModelFit
from .base_analysis import AnalysisNode
from ressources import custom_types
from model.base_objects import DerivedSignalObject,SignalObject


def thermal_step(t, T_inf, tau, T0):
    """Réponse thermique à échelon : T(t) = T_inf - (T_inf-T0)*exp(-t/tau)"""
    #=> avantage : formule simple, peu de paramètres, interprétation physique directe
    # (croissante comme décroissante selon T_inf vs T0)
    #=> inconvénient : ne modélise pas les phénomènes plus complexes
    # (ex: réponse à une entrée variable, non-linéarités, etc.)

    return T_inf - (T_inf - T0) * np.exp(-t / tau)


class ThermalModelAnalysis(AnalysisNode):
    """
    Analyse thermique RC (1er ordre) sur un signal temporel.
    """
    # projection automatique : la courbe modèle est prolongée jusqu'à N_TAU constantes de
    # temps depuis le début de la plage de fit (5 tau : 99.3 % de l'écart final)
    N_TAU = 5
    # Réutilise un type existant ou ajoute un nouveau
    action_type = custom_types.qSignalType.MODEL
    PARAMETER_SCHEMA = {
        "Model": {
                        "type": "list",
                        "default": "RC_step",
                        "limits": ["RC_step"],
                        "key": "model_type",
                },
        "Auto projection (5 τ)": {
                        "type": "bool",
                        "default": True,
                        "key": "projection_auto",
                        "description": "Courbe modèle prolongée jusqu'à 5 tau (asymptote "+
                                        "atteinte à 99 %). Saisir une durée repasse en manuel"
                        },
        "Projection duration (s)": {
                        "type": "float",
                        "default": 0.0,
                        "limits": (0, None),
                        "suffix": "s",
                        "key": "projection_duration",
                        "description": "Durée de la courbe modèle après la fin de la plage "+
                                        "de fit (calculée en mode auto)"
                        },
        # [t_start, t_end] des données d'entrée du modèle (None = tout l'enregistrement).
        # Définie à la création par la sélection de plage du graphique, puis éditable
        # avec les curseurs du ParameterTree.
        'Model definition range':{
                        "type": "cursors",
                        "visible":True,
                        "default": None,
                        "expanded" : True,
                        "cursors_setting":{
                                'angle':90,
                                'pos':[0,1200],
                                'pen':pg.mkPen(color = 'r'),
                                'label':'{value:0.0f}s',
                                'labelOpts':{   
                                                'color': (200,0,0),
                                                'fill':(200,200,200,100),
                                                'movable': True
                                            }
                                },
                        "key": "model_range",
                        },
        "User estimated power input (W)": {
                        "type": "float",
                        "default": 100.0,
                        "suffix": "W",
                        "key": "power",
                        "description": "Puissance introduite (W)"
                        },
        "User estimated heat capacity": {
                        "type": "float",
                        "default": 1.0,
                        "suffix": "J/K",
                        "key": "heat_capacity",
                        "description": "Capacité thermique estimée (J/K)"
                        }
    }
    # --------------------------------------------------
    # Configuration
    # --------------------------------------------------

    @property
    def display_name(self) -> str:
        return f"Thermal Model ({self.get_param('model_type')})"


    def validate(self, params):
        if params['projection_duration'] < 0:
            raise ValueError("Extrapolation time must be >= 0")

        model_range = params['model_range']
        if model_range is not None:
            if len(model_range) != 2:
                raise ValueError("Model range must be [t_start, t_end]")
            if float(model_range[1]) <= float(model_range[0]):
                raise ValueError("Model range: t_end must be greater than t_start")

        # self.id est attribué par AnalysisNode.__init__ : il sert de clé dans
        # signal.analyses et ne doit pas changer à chaque validation
        # t_start / t_end : plage EFFECTIVE du dernier fit (model_range bornée aux données)
        self.t_start = None
        self.t_end = None
        self.results: custom_items.ThermalFitResult | None = None
        self._x_fitted = None
        self._y_fitted = None
        self._x_model = None
        self._y_model = None

        #! pourquoi ne pas utilser setAttr pour assigner les paramètres directement à l'objet ?
        #! (ex: self.model_type = params['model_type'])
        #print(f'AnalysisNode créée: {self.opts_dict}')

    def set_fit_range(self, t_start: float, t_end: float):
        if t_end <= t_start:
            raise ValueError("t_end must be greater than t_start")
        self.t_start = t_start
        self.t_end = t_end

    # --------------------------------------------------
    # Analyse principale
    # --------------------------------------------------

    def run(self, x: np.ndarray, y: np.ndarray, power: float):
        """
        Lance l'analyse thermique.

        Args:
            x (np.ndarray): temps (s)
            y (np.ndarray): température
            power (float): puissance introduite (W)
        """

        if self.t_start is None or self.t_end is None:
            raise RuntimeError("Fit range not defined")

        # --- Troncature ---
        mask = (x >= self.t_start) & (x <= self.t_end)
        x_fit = x[mask] - x[mask][0]   # temps relatif
        y_fit = y[mask]

        if len(x_fit) < 5:
            raise RuntimeError("Not enough data points for fitting")

        # --- Valeurs initiales ---
        T0 = y_fit[0]
        T_inf_guess = y_fit[-1]
        tau_guess = (x_fit[-1] - x_fit[0]) / 3

        p0 = [T_inf_guess, tau_guess, T0]

        # --- Fit ---
        params, _ = curve_fit(
                                thermal_step,
                                x_fit,
                                y_fit,
                                p0=p0,
                                maxfev=10000
                            )

        T_inf, tau, T0 = params

        # --- Paramètres physiques ---
        R_th = (T_inf - T0) / power
        C_th = tau / R_th

        # --- Erreur ---
        y_pred = thermal_step(x_fit, *params)

        if abs(T_inf) > 15 * max(abs(y_fit)):
            raise InvalidModelFit(
                "T_inf est physiquement incohérent avec les données"
            )

        if tau > 100 * x_fit[-1] or tau <0:
            raise InvalidModelFit(
                "Constante de temps irréaliste (tau >> durée de mesure)"
            )

        rmse = np.sqrt(np.mean((y_pred - y_fit) ** 2))

        # --- Stockage ---
        self.results = custom_items.ThermalFitResult(
                                        tau=tau,
                                        R_th=R_th,
                                        C_th=C_th,
                                        T_inf=T_inf,
                                        T0=T0,
                                        rmse=rmse
                                    )

        self._x_fitted = x_fit
        self._y_fitted = y_pred

        return self.results

    # --------------------------------------------------
    # Génération de la courbe modèle (projection)
    # --------------------------------------------------

    def generate_model_curve(self):
        if self.results is None:
            raise RuntimeError("Analysis not run")

        tau = self.results.tau
        T0 = self.results.T0
        T_inf = self.results.T_inf

        t_end = self._x_fitted[-1]
        if self.get_param('projection_auto'):
            projection_duration = max(0.0, self.N_TAU * tau - t_end)
            # valeur calculée conservée dans les paramètres : affichée dans le
            # ParameterTree et sauvegardée avec le projet
            self._params['projection_duration'] = float(projection_duration)
        else:
            projection_duration = self.get_param('projection_duration')

        t_model = np.linspace(0, t_end + projection_duration, 500)
        y_model = thermal_step(t_model, T_inf, tau, T0)

        self._x_model = t_model
        self._y_model = y_model

        return t_model, y_model

    # --------------------------------------------------
    # Export / sérialisation
    # --------------------------------------------------

    @staticmethod
    def upgrade_params(params: dict) -> dict:
        """
        Paramètres d'un projet sauvegardé -> paramètres actuels (appelé par AnalysisFactory
        au rechargement). Avant la prise en compte des bornes, model_range valait le défaut
        [0, 1200] ou le dict des curseurs, sans jamais être appliqué : le fit était fait sur
        tout l'enregistrement, ce que l'on conserve (None).
        """
        params = dict(params)
        model_range = params.get('model_range')
        if isinstance(model_range, dict) or model_range == [0, 1200]:
            params['model_range'] = None
        # avant le mode auto explicite, une durée de projection nulle signifiait « auto »
        if 'projection_auto' not in params:
            params['projection_auto'] = not params.get('projection_duration', 0)
        return params

    def clone_with(self, **new_params):
        """
        Saisir une durée de projection (différente de la valeur calculée) en mode auto
        repasse le modèle en projection manuelle.
        """
        auto = self.get_param('projection_auto')
        duration = new_params.get('projection_duration', self.get_param('projection_duration'))
        if (auto and new_params.get('projection_auto', auto) == auto
                and duration != self.get_param('projection_duration')):
            new_params['projection_auto'] = False
        return super().clone_with(**new_params)

    def to_dict(self):
        # "type" + "params" (paramètres d'ENTRÉE) : c'est ce qu'attend AnalysisFactory
        # au rechargement, le fit est ensuite recalculé.
        data = super().to_dict()
        # résultats du fit : informatifs (export), ignorés au rechargement
        if self.results is not None:
            data["results"] = {
                                "tau"       :    float(self.results.tau),
                                "R_th"      :    float(self.results.R_th),
                                "C_th"      :    float(self.results.C_th),
                                "T0"        :    float(self.results.T0),
                                "T_inf"     :    float(self.results.T_inf),
                                "rmse"      :    float(self.results.rmse),
                                "fit_range" :    (float(self.t_start), float(self.t_end))
                                }
        return data



    def compute( self,  parent_signal):
        """
        Génère un SignalObject à partir du modèle thermique.
        """
        # Utilise les données après pipeline
        x = parent_signal.x
        y = parent_signal.y

        # plage de fit : model_range bornée aux données, tout l'enregistrement par défaut
        model_range = self.get_param('model_range')
        if model_range is None:
            self.set_fit_range(float(x[0]), float(x[-1]))
        else:
            t_start = max(float(model_range[0]), float(x[0]))
            t_end   = min(float(model_range[1]), float(x[-1]))
            if t_end <= t_start:
                raise RuntimeError("Model range does not overlap the signal")
            self.set_fit_range(t_start, t_end)
        self.results=self.run(x,y,self.get_param('power'))

        x_model, y_model = self.generate_model_curve()

        # Décalage temporel si nécessaire
        x_model = x_model + self.t_start

        name = f"{parent_signal.name} (model RC)"

        pen = pg.mkPen(color=parent_signal.pen.color(), width=2, style=Qt.PenStyle.DashLine)

        # Métadonnées utiles
        metadata = {
                                "type": "thermal_model",
                                "source": parent_signal.name,
                                "analysis_id": self.id,
                                "params": self.to_dict()
                            }

        #print(metadata)
        model_signal = DerivedSignalObject(
                                    parent_signal=parent_signal,
                                    name=name,
                                    x=x_model,
                                    y=y_model,
                                    pen=pen,
                                    metadata=metadata
                                )

        return model_signal

'''        "Model left range limit": {
                        "type": "cursor",
                        "default": 0.0,
                        "key": "t_start",
                        "description": "Borne gauche de la plage des données d'entrée"+
                                        "du modèle."
                        },
        "Model right range limit": {
                        "type": "float",
                        "default": 100.0,
                        "key": "t_end",
                        "description": "Borne droite de la plage des données d'entrée"+
                                        "du modèle."
                        }'''