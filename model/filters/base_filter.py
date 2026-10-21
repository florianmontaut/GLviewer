# model/filters/base_filter.py

from abc import ABC, abstractmethod
import uuid

from ressources.custom_types import qSignalType
from ressources.custom_items import itemType
from ressources.custom_struct_functions import (generate_opts_dict,extract_parameter_values,
                                                apply_options_to_parameters)

class  FilterNode(ABC):
    """
    Classe de base pour tous les filtres, c'est une Classe Abstraite donnant
    le squelette de tous les FilterNodes héritant de cette classe
    """

    #  identité logique IMMUTABLE (utilisée pour JSON, undo, factory)
    item_type = itemType.FILTER
    action_type : qSignalType
    PARAMETER_SCHEMA: dict = {}

    def __init__(self, **params):
        # stockage unique des paramètres dict permet de faire un copie
        # et surtout pas une nouvelle référence au même objet. Ici on ne
        # récupère que la valeur par défaut du schéma qui passée dans la
        # classe de l'objet !
        self.is_selected = False
        self.id = uuid.uuid4().hex
        self.opts_dict = generate_opts_dict(self.PARAMETER_SCHEMA)
        self._params = {
                            self.opts_dict[name]: spec["default"] for name,
                            spec in self.PARAMETER_SCHEMA.items()
                        }

        self.set_params(**params)

    # -------------------------------------------------
    # PARAMÈTRES
    # -------------------------------------------------

    def set_param(self, name,val):
        self._params[name] = val

    def set_params(self, **params):
        """Modifie les paramètres avec validation."""
        new = {**self._params, **params}
        self.validate(new)
        self._params = new

    def get_param(self, name):
        return self._params[name]

    def get_params(self) -> dict:
        return dict(self._params)

    # -------------------------------------------------
    # VALIDATION (DSP invariants)
    # -------------------------------------------------
    @abstractmethod
    def validate(self, params: dict):
        """Doit lever ValueError si invalide."""
        pass

    # -------------------------------------------------
    # CALCUL
    # -------------------------------------------------
    @abstractmethod
    def apply(self, x, y):
        """Applique le filtre sur y."""
        pass

    # -------------------------------------------------
    # AFFICHAGE
    # -------------------------------------------------
    @property
    @abstractmethod
    def display_name(self) -> str:
        pass

    # -------------------------------------------------
    # SÉRIALISATION
    # -------------------------------------------------
    def to_dict(self):
        return {
            "type": self.action_type.name,
            "params": self.get_params()
        }

    @classmethod
    def from_dict(cls, data: dict):
        return cls(**data["params"])

    # -------------------------------------------------
    # UNDO / REDO SAFE
    # -------------------------------------------------
    def clone_with(self, **new_params):
        return type(self)(**{**self._params, **new_params})
