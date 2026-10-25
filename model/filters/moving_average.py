
# model/filters/moving_average.py

import numpy as np
from .base_filter import FilterNode
from ressources.custom_types import qSignalType

class MovingAverageFilter(FilterNode):

    action_type = qSignalType.AVG
    PARAMETER_SCHEMA = {
                        "Largeur de la fenêtre": {
                                                "type": "int",
                                                "default": 5,
                                                "limits": (1, None),
                                                "readonly": False,
                                                "key":"window",
                                            }
                        }

    def validate(self, params):
        if not isinstance(params['window'], int):
            raise ValueError("Window must be an integer")

    @property
    def display_name(self) -> str:
        return f"MovingAvg({self.get_param('window')})"

    def apply(self, x, y):
        # moyenne des seuls échantillons valides de la fenêtre : les données manquantes
        # (NaN) ne contaminent pas leurs voisines, et les bords du signal ne sont plus
        # tirés vers 0 (np.convolve complétait la fenêtre par des zéros)
        w = self.get_param('window')
        y = np.asarray(y, dtype=float)
        valid = np.isfinite(y)
        kernel = np.ones(w)
        total = np.convolve(np.where(valid, y, 0.0), kernel, mode="same")
        count = np.convolve(valid.astype(float), kernel, mode="same")
        with np.errstate(invalid="ignore", divide="ignore"):
            out = total / count
        out[~valid] = np.nan
        return out