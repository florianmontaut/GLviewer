import numpy as np
import copy
from pandas import DataFrame
from PyQt6.QtWidgets import  QTreeWidgetItem
from PyQt6 import QtGui,QtCore

from dataclasses import dataclass,field

import pyqtgraph as pg
import pyqtgraph.parametertree as ptree

from .custom_parameters import ComplementaryElements
from .custom_tree_functions import CustomTreeWidget
from .custom_types import itemType,qSignalType,ActionModifier,fileType

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

    name         :   str= field(init=False)
    address      :   str
    file_type    :   str
    sampling     :   float
    n_samples    :   int
    recordDate   :   str
    validTable   :   list[bool]
    data         :   DataFrame

    def __post_init__(self):
        self.name : str = self.address[self.address.rfind('/')+1:len(self.address)-4]
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



@dataclass
class AddDescriptor:
    action_modifier: ActionModifier
    action_type: qSignalType
    params: dict


@dataclass
class ActionRequest(AddDescriptor):
    index: int
    model: object  = field(init=False,default=None)

@dataclass
class ThermalFitResult:
    tau: float
    R_th: float
    C_th: float
    T_inf: float
    T0: float
    rmse: float

    def to_dict(self):

        return  {k: v for k, v in self.__dict__.items() }
    

@dataclass(frozen=True)
class ImportRequest:
    file_format: fileType
    loader_label : tuple
    loader: callable