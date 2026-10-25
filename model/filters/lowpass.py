
# model/filters/lowpass.py

import numpy as np
from scipy.signal import butter, filtfilt
from .base_filter import FilterNode
from model.missing_data import fill_gaps
from ressources.custom_types import qSignalType


class LowPassFilter(FilterNode):
    """Low-band frequency filter

    Args:
        cutoff  (float)  : cut-off frequency of the filter
        fs      (float)  : sampling frequency
        order   (int)    : ordre du filtre

    Raises:
        ValueError: fs must be strictely positive
        ValueError: cutoff must be strictely positive
        ValueError: cutoff must be smaler or equal to fs/2
        ValueError: order must be greater or equal to 1

    Returns:
        _type_: _description_
    """

    action_type = qSignalType.FILTER
    # le dictionnaire ci-dessous donne les valeurs par défaut des arguments et
    # mais également la structure des paramètres à afficher dans le parameterTree
    # (voir parameter_controller)

    #! actuelement le filtre charge la fréquence de coupure par défaut, et ce malgré que
    #! la méthode _pipeline_add_filter du main_controller passe 0.03 en argument !
    PARAMETER_SCHEMA = {
                        "Cut-off frequency": {
                                            "type": "float",
                                            "default": 0.002,
                                            "limits": (1e-6, None),
                                            "suffix": "Hz",
                                            "readonly": False,
                                            "key":"cutoff",
                        },
                        "Sampling frequency": {
                                            "type": "float",
                                            "default": 1.0,
                                            "limits": (1e-9, None),
                                            "suffix": "Hz",
                                            "readonly": False,
                                            "key":"fs",
                        },
                        "Filter order": {
                                        "type": "int",
                                        "default": 2,
                                        "limits": (1, 10),
                                        "readonly": False,
                                        "key":"order",
                                        }
                    }


    def validate(self, params):

        if params['fs'] <= 0:
            raise ValueError('fs must be > 0')
        if params['cutoff'] <= 0:
            raise ValueError('cutoff must be > 0')
        if params['cutoff'] >= params['fs']/2:
            raise ValueError('cutoff must be < fs/2')
        if params['order'] <1:
            raise ValueError('order must be >= 1')

    @property
    def display_name(self) -> str:
        return f"LowPass (fc={self.get_param('cutoff')}Hz, order={self.get_param('order')})"

    def apply(self, x, y):

        b, a = butter(self.get_param('order'), self.get_param('cutoff')/(0.5*self.get_param('fs')))
        # filtfilt propage un NaN à tout le signal : les trous sont comblés le temps du
        # filtrage, puis remis (données manquantes, voir model.missing_data)
        filled, missing = fill_gaps(x, y)
        if missing.all():
            return filled.copy()
        out = filtfilt(b, a, filled)
        out[missing] = np.nan
        return out
