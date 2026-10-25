import os
import numpy as np
import copy
from pandas import DataFrame
from PyQt6.QtWidgets import  QTreeWidgetItem
from PyQt6 import QtGui,QtCore

from dataclasses import dataclass,field
from typing import Optional

import pyqtgraph as pg
import pyqtgraph.parametertree as ptree

from ressources.custom_parameters import ComplementaryElements
from ressources.custom_tree_functions import CustomTreeWidget
from ressources.custom_types import itemType,qSignalType,ActionModifier,fileType
#from model.base_objects import SignalObject
from model.tree_item import TreeItem

@dataclass
class StandardStruct():

    name         :   str
    item_id      :   list[int]
    item_type    :   itemType = field(init=False)
    _absolute_id :   int

    def __repr__(self):
        kws = [f"{key}={value!r}" for key, value in self.__dict__.items()]
        return "{}({})".format(type(self).__name__, ", ".join(kws))

@dataclass
class FileStruct():

    name            :   str= field(init=False)
    address         :   str
    file_type       :   str
    sampling        :   float
    n_samples       :   int
    recordDate      :   str
    import_params   :   dict
    data            :   DataFrame

    def __post_init__(self):
        #os.path gère les séparateurs '/' et '\' sous Windows (et les extensions != 3 lettres)
        self.name : str = os.path.splitext(os.path.basename(self.address))[0]
        self.start_x : float = 0
        self.stop_x : float = 0
        self.offset : int  = 0

@dataclass
class RawStruct(StandardStruct):

    fc           :   float
    pen          :   QtGui.QPen
    color        :   QtGui.QColor = field(init=False)

    def __post_init__(self):
        self.item_type=itemType.RAW
        self.color=self.pen.color()

@dataclass
class ModifStruct(RawStruct):

    input_id    :  int
    modification :  str
    fc : float

    def __post_init__(self):
        self.item_type=itemType.MODIF
        self.color=self.pen.color()

    def ItemParameters(self):
        pass

@dataclass
class ModelStruct(ModifStruct):

    modelFunc    : str
    modelCoef    : list[float]
    modification : str = field(init=False,default=None)
    polyDeg      : int = field(init=False,default=3)
    fc           : float = field(init=False,default=None)
    start_x      : int
    stop_x       : int

    def __post_init__(self):
        self.item_type=itemType.MODEL
        self.color=self.pen.color()

    def itemParameters(self):
        listCoef=[np.format_float_scientific(val, unique=False, precision=5)
                    for val in self.modelCoef]
        return ''.join(['\t'.join(listCoef)])






@dataclass(frozen=True)
class SelectionContext:
    role:               itemType
    signal:             object
    filter_id:          Optional[str] = None
    analysis_id:        Optional[str] = None
    item:               Optional[TreeItem] = None
    
    
    def __post_init__(self):
        if self.filter_id is not None and self.analysis_id is not None:
            raise ValueError(
                "SelectionContext cannot reference both filter_id and analysis_id."
            )

    
    #! à supprimer
    '''    
    derived_index:      Optional[int] = None
    
    '''
    #! à supprimer
    
    def get_filter(self):
        
        if self.filter_id is None:
            return None
        return self.signal.get_filter_by_id(self.filter_id)

    def get_analysis(self):
        
        if self.analysis_id is None:
            return None
        return self.signal.get_analysis_by_id(self.analysis_id)

    def get_node(self):
        if self.filter_id is not None:
            return self.get_filter()
        if self.analysis_id is not None:
            return self.get_analysis()

        return self.signal
    
    def get_node_index(self):
        if self.analysis_id is None:
            return self.signal.get_node_index(filter_id=self.filter_id)
        elif self.filter_id is None:
            return self.signal.get_node_index(analysis_id=self.analysis_id)
        else:
            return None
        

    # ------------------------------------------------------------------
    # Temporary backward compatibility with index-based code
    # ------------------------------------------------------------------

    @property
    def filter_index(self):
        if self.filter_id is None:
            return None
        return self.signal.get_filter_index_by_id(self.filter_id)

    @property
    def analysis_index(self):
        if self.analysis_id is None:
            return None
        return self.signal.get_analysis_index_by_id(self.analysis_id)

    def get_node_index(self):
        if self.filter_id is not None:
            return self.filter_index

        if self.analysis_id is not None:
            return self.analysis_index

        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def is_signal(self):
        return self.filter_id is None and self.analysis_id is None

    @property
    def is_filter(self):
        return self.filter_id is not None

    @property
    def is_analysis(self):
        return self.analysis_id is not None




@dataclass
class AddDescriptor:
    action_modifier: ActionModifier
    action_type:     qSignalType
    params:          dict


@dataclass
class ActionRequest(AddDescriptor):
    index: int
    model: object  = field(init=False,default=None)



@dataclass(frozen=True)
class ModelChangeEvent:
    action: ActionModifier
    context: SelectionContext








@dataclass
class ThermalFitResult:
    tau: float
    R_th: float
    C_th: float
    T_inf: float
    T0: float
    rmse: float
    # puissance utilisée pour Rth (W) et sa plage sur l'intervalle de fit (voie de
    # puissance : moyenne, min et max ; valeur manuelle : identiques)
    power: float = 0.0
    power_min: float = 0.0
    power_max: float = 0.0
    power_channel: str = ""

    def to_dict(self):

        return  {k: v for k, v in self.__dict__.items() }


@dataclass(frozen=True)
class ImportRequest:
    file_format: fileType
    loader_label : tuple
    loader: callable



