
# model/filters/offset.py
import numpy as np

from .base_filter import FilterNode
from ressources.custom_types import qSignalType

# Plus __init__ le package abc, et sa classe ABC permet de passer
# l'ensemble de méthode au classe qui en hérite, pas besoin de les surcharger
class OffsetFilter(FilterNode):
    """_summary_

    Args:
        FilterNode (_type_): _description_

    Raises:
        ValueError: _description_

    Returns:
        _type_: _description_
    """

    action_type = qSignalType.OFFSET
    PARAMETER_SCHEMA = {
                        "Y offset": {
                                    "type": "float",
                                    "default": 0,
                                    "readonly": False,
                                    "key": "offset"
                                    }
                    }
    # voir Filter node pour comprendre le chargement des attributs _params et autres
    # PARAMETER_DEFAULTS étant chargé avant que validate ne soit appelé
    def validate(self, params):

        if not isinstance(params["offset"], (int, float)):
            raise ValueError("Offset must be numeric")

    @property
    def display_name(self) -> str:
        return f'Offset({self.get_param("offset"):g})'

    def apply(self, x, y):

        return y + np.ones(len(y))*self.get_param("offset")
