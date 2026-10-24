
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING
import uuid

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
        self.is_selected = False
        self.id = uuid.uuid4().hex
        # échec du dernier recalcul automatique (voir SignalObject.refresh_derived)
        self.error = None
        self._error_key = None
        self.opts_dict = generate_opts_dict(self.PARAMETER_SCHEMA)
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

    def display_param(self, key, parent_signal):
        """
        Valeur d'un paramètre telle qu'affichée (ParameterTree). Par défaut, la valeur
        stockée ; voir ThermalModelAnalysis (plage en temps de l'enregistrement).
        """
        return self.get_param(key)

    def input_key(self, parent_signal) -> tuple:
        """
        État des données d'entrée de l'analyse : si il change, les signaux dérivés sont
        périmés (voir SignalObject.refresh_derived).
        """
        return parent_signal.input_key()

    def derive(self, parent_signal) -> 'DerivedSignalObject':
        """
        Calcule le signal dérivé (compute) et lui associe l'état des données d'entrée
        ayant servi au calcul (metadata['input_key']).
        """
        derived = self.compute(parent_signal)
        derived.metadata.setdefault('analysis_id', self.id)
        derived.metadata['input_key'] = self.input_key(parent_signal)
        return derived

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
