
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
            raise ValueError("Offset must be numeric")

    @property
    def display_name(self) -> str:
        return f"MovingAvg({self.get_param('window')})"

    def apply(self, x, y):
        w = self.get_param('window')
        return np.convolve(y, np.ones(w)/w, mode="same")