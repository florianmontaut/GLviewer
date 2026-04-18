
import uuid
import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import Qt
from scipy.optimize import curve_fit

from ressources import custom_items, custom_struct_functions
from .base_analysis import AnalysisNode
from ressources import custom_types
from model.base_objects import DerivedSignalObject,SignalObject


def thermal_step(t, T_inf, tau, T0):
    """Réponse thermique à échelon : T(t) = T_inf - (T_inf-T0)*exp(-t/tau)"""
    return T_inf - (T_inf - T0) * np.exp(-t / tau)



#! Repartir d'analysisNode!
class ThermalModelAnalysis(AnalysisNode):
    """
    Analyse thermique RC (1er ordre) sur un signal temporel.
    """
    # Réutilise un type existant ou ajoute un nouveau
    action_type = custom_types.qSignalType.MODEL
    PARAMETER_SCHEMA = {
        "Model": {
                        "type": "list",
                        "default": "RC_step",
                        "limits": ["RC_step"],
                        "key": "model_type",
                },
        "Projection duration (s)": {
                        "type": "float",
                        "default": 0.0,
                        "key": "projection_duration",
                        "description": "Durée supplémentaire pour projeter"+
                                        "la courbe après la fin du signal"
                        }
    }

    def __init__(self, label=None):

        self.id = uuid.uuid4().hex[:8]
        super().__init__()
        self.t_start = None
        self.t_end = None
        self.results: custom_items.ThermalFitResult | None = None
        self._x_fitted = None
        self._y_fitted = None
        self._x_model = None
        self._y_model = None
        self.opts_dict = custom_struct_functions.generate_opts_dict(self.PARAMETER_SCHEMA)
        print(f'AnalysisNode créée: {self.opts_dict}')

    # --------------------------------------------------
    # Configuration
    # --------------------------------------------------

    @property
    def display_name(self) -> str:
        return f"Thermal Model ({self.get_param('model_type')})"


    def validate(self, params):
        if params['projection_duration'] < 0:
            raise ValueError("Extrapolation time must be >= 0")
        #! ajouter une vérif sur la validité de la plage (start et stop).

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
        projection = max(t_end * 3, t_end + 5 * tau)

        t_model = np.linspace(0, projection, 500)
        y_model = thermal_step(t_model, T_inf, tau, T0)

        self._x_model = t_model
        self._y_model = y_model

        return t_model, y_model

    # --------------------------------------------------
    # Export / sérialisation
    # --------------------------------------------------

    def to_dict(self):
        if self.results is None:
            return {}

        return {
            "tau": self.results.tau,
            "R_th": self.results.R_th,
            "C_th": self.results.C_th,
            "T0": self.results.T0,
            "T_inf": self.results.T_inf,
            "rmse": self.results.rmse,
            "fit_range": (self.t_start, self.t_end),
        }



    def compute( self,  parent_signal):
        """
        Génère un SignalObject à partir du modèle thermique.
        """
        # Utilise les données après pipeline
        x = parent_signal.x
        y = parent_signal.y

        if self.t_start is None:
            self.t_start = x[0]
        if self.t_end is None:
            self.t_end = x[-1]
        self.results=self.run(x,y,100)

        if self.results is None:
            raise RuntimeError("Model not computed")

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

        print(metadata)
        model_signal = DerivedSignalObject(
                                    parent_signal=parent_signal,
                                    name=name,
                                    x=x_model,
                                    y=y_model,
                                    pen=pen,
                                    metadata=metadata
                                )

        return model_signal


class ThermalAnalysis(AnalysisNode):
    """Analyse thermique : ajuste un modèle RC et extrapole à l'asymptotique."""
    # Réutilise un type existant ou ajoute un nouveau
    action_type = custom_types.qSignalType.MODEL
    PARAMETER_SCHEMA = {
        "Model Type": {
            "type": "list",
            "default": "1st_order",
            "values": ["1st_order", "2nd_order", "polynomial"],
            "readonly": False,
            "key": "model_type",
        },
        "Polynomial Degree": {
            "type": "int",
            "default": 2,
            "limits": (1, 10),
            "readonly": False,
            "key": "poly_deg",
        },
        "Extrapolation Time (s)": {
            "type": "float",
            "default": 1000.0,  # Temps d'extrapolation au-delà des données
            "limits": (0, None),
            "suffix": "s",
            "readonly": False,
            "key": "extrap_time",
        },
    }

    def validate(self, params):
        if params['extrap_time'] < 0:
            raise ValueError("Extrapolation time must be >= 0")

    @property
    def display_name(self) -> str:
        return f"Thermal Model ({self.get_param('model_type')})"

    def compute(self, parent_signal):
        x = parent_signal.x
        y = parent_signal.y  # Utilise les données après pipeline

        # Ajustement du modèle (simplifié, utilise tes modèles existants)
        if self.get_param('model_type') == 'polynomial':
            params = np.polyfit(x, y, self.get_param('poly_deg'))
            model_func = lambda t: np.polyval(params, t)
        else:
            # Exemple pour 1st_order (RC) - remplace par tes vraies fonctions
            model_func = lambda t, tau, asymptote: asymptote * (1 - np.exp(-t / tau))
            params, _ = curve_fit(model_func, x, y, p0=[100, y[-1]])

        # Extrapolation : étend x au-delà des données originales
        max_x = x[-1] + self.get_param('extrap_time')
        # Densifie pour lissage
        x_extrap = np.linspace(x[0], max_x, int((max_x - x[0]) / (x[1] - x[0])) * 2)
        y_extrap = model_func(x_extrap, *params) if self.get_param('model_type') != (
                                                'polynomial') else model_func(x_extrap)

        # Crée un DerivedSignalObject avec les données extrapolées
        derived_name = f"{parent_signal.name}_thermal_model"
        pen = parent_signal.pen
        #pen = pg.mkPen(color="blue", style=Qt.PenStyle.DashLine)
        derived_signal = DerivedSignalObject(
            parent_signal=parent_signal,
            name=derived_name,
            x=x_extrap,
            y=y_extrap,
            pen=pen,
            metadata={  "params"    : params,
                        "model_type": self.get_param('model_type')
                    }
        )
        return derived_signal
