
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from model.base_objects import SignalObject, DerivedSignalObject

from ressources.custom_types import qSignalType
from ressources.custom_items import itemType

from ressources.custom_struct_functions import (generate_opts_dict, extract_parameter_values,
                                                apply_options_to_parameters)


##### 2eme solution github


class AnalysisNode(ABC):
    """
    Classe de base pour toutes les analyses (symétrique à FilterNode).
    """
    item_type = itemType.ANALYSE
    action_type: qSignalType
    PARAMETER_SCHEMA: dict = {}

    def __init__(self, **params):
        # Initialisation des paramètres depuis le schéma
        self._params = {
                            spec["key"]: spec["default"]
                            for spec in self.PARAMETER_SCHEMA.values()
                        }
        self.set_params(**params)

    # ---------------- PARAMÈTRES ----------------

    def set_param(self, key, val):
        self._params[key] = val

    def set_params(self, **params):
        new = {**self._params, **params}
        self.validate(new)
        self._params = new

    def get_param(self, key):
        return self._params[key]

    def get_params(self) -> dict:
        return dict(self._params)

    # ---------------- VALIDATION ----------------

    @abstractmethod
    def validate(self, params: dict):
        pass

    # ---------------- CALCUL ----------------

    @abstractmethod
    def compute(self, parent_signal: 'SignalObject') -> 'DerivedSignalObject':
        pass

    # ---------------- AFFICHAGE ----------------

    @property
    @abstractmethod
    def display_name(self) -> str:
        pass

    # ---------------- SÉRIALISATION ----------------

    def to_dict(self):
        return {
            "type": self.action_type.name,
            "params": self.get_params()
        }

    @classmethod
    def from_dict(cls, data):
        return cls(**data["params"])

    # ---------------- IMMUTABILITÉ ----------------

    def clone_with(self, **new_params):
        return type(self)(**{**self._params, **new_params})
