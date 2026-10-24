# model/filters/diff.py

import numpy as np

from .base_filter import FilterNode
from ..base_objects import SignalObject
from ressources.custom_types import qSignalType

class DiffFilter(FilterNode):

    action_type = qSignalType.DIFF

    PARAMETER_SCHEMA = {
                        "Reference signal": {
                                    "type": "signal",
                                    "default": None,
                                    "readonly": False,
                                    "description": "Reference signal for difference",
                                    "key":"reference"
                                    }
                        }

    def validate(self,params):

        if isinstance(params['reference'], SignalObject):
            pass
        elif  isinstance(params['reference'], str):
            self._reference_name = params['reference']
        else:
            raise ValueError('A reference signal must be a selected or a signal name passed')

    def get_params(self):
        if isinstance(self.get_param('reference'), SignalObject):
            return {'reference': self.get_param('reference').name}
        else:
            return {'reference': self.get_param('reference')}

    @property
    def display_name(self) -> str:
        #voir méthode ci-dessus, ne pas remplacer par  get_param !!
        return f"Diff ({self.get_params()['reference']})"

    def apply(self, x, y):
        ref = self.get_param('reference')

        if not isinstance(self.get_param('reference'), SignalObject):
            raise RuntimeError("No reference signal defined for DiffFilter")

        ref_x, ref_y = ref.x, ref.y
        if len(ref_x) == len(x) and np.array_equal(ref_x, x):
            return y - ref_y
        # axes des temps différents (décalage temporel d'une des voies) : la référence est
        # interpolée aux instants du signal, NaN hors de sa plage
        return y - np.interp(x, ref_x, ref_y, left=np.nan, right=np.nan)

    def resolve_reference(self, signal_map: dict):
        if (    not isinstance(  self.get_param('reference'), SignalObject)
                and hasattr(self,'_reference_name')):
            
            self.set_param('reference', signal_map.get(self._reference_name))
            if self.get_param('reference') is None:
                raise ValueError(
                    f"Reference signal '{self._reference_name}' not found"
                )
