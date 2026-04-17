# model/filters/time_shift.py

from .base_filter import FilterNode
from ressources.custom_types import qSignalType

class TimeShiftFilter(FilterNode):


    action_type = qSignalType.OFFSET_X
    PARAMETER_SCHEMA = {
                        "Time shift (s)": {
                                            "type": "float",
                                            "default": 0.0,
                                            "key": "shift_seconds",
                                        }
                    }

    def validate(self, params):

        if not isinstance(params["shift_seconds"], (int, float)):
            raise ValueError("Offset must be numeric")

    @property
    def display_name(self) -> str:
        return f'Time shift (s)({self.get_param("shift_seconds"):g})'

    def apply(self, x, y):
        shift = self.get_param("shift_seconds")
        return x + shift, y
