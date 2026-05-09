
# model/base_objects.py

from PyQt6 import QtCore, QtGui

import numpy as np
import pandas as pd
import json

from dataclasses import dataclass,field
from typing import Optional

import pyqtgraph as pg
import pyqtgraph.parametertree as ptree


from ressources import custom_parameters,custom_struct_functions
from ressources.custom_items import itemType,FileStruct
from model.tree_item import TreeItem




class FileObject:
    """
    Représente un fichier chargé (CSV, CAN, UDP...), contenant :

    - un DataFrame complet
    - tous les SignalObject (raw + calculés)
    """


    item_type = itemType.FILE
    PARAMETER_SCHEMA= {
                        'File name'    :{
                                            'type':'str',
                                            'default':None,
                                            "readonly": True,
                                            "key": "name"
                                        },
                        'File editor' :{
                                            'type': 'group',
                                            'expanded':True,
                                            'children':
                                                    {
                                                    'Time offset':{
                                                                        'type':'float',
                                                                        'default':0.0,
                                                                        'suffix': "s",
                                                                        "readonly": False,
                                                                        "key": "offset"
                                                                        },
                                                    'Truncate left':{
                                                                        'type':'float',
                                                                        'default':0.0,
                                                                        'limits':[0.0,None],
                                                                        "suffix": "s",
                                                                        "readonly": False,
                                                                        "key": "start_x"
                                                                        },
                                                    'Truncate right':{
                                                                        'type':'float',
                                                                        'default':0.0,
                                                                        'limits':[0.0,None],
                                                                        "suffix": "s",
                                                                        "readonly": False,
                                                                        "key": "stop_x"
                                                                        }
                                                    }
                                        }
                    }

    n_colors=20

    def __init__(self, fileData : FileStruct ):

        for key,val in fileData.__dict__.items():
            setattr(self,key,val)

        self.address        :   str
        self.sampling       :   float
        self.n_samples      :   int
        self.recordDate     :   str
        self.import_params  :   list[bool]
        self.data           :   pd.DataFrame
        self.name           :   str
        self.file_type      :   str
        self.start_x        :   float
        self.stop_x         :   float
        self.offset         :   int

        self.signals = []   # Liste de SignalObject
        self.is_selected = False
        self.opts_dict = custom_struct_functions.generate_opts_dict(self.PARAMETER_SCHEMA)
        self.colormap = pg.colormap.getFromMatplotlib('tab20')
        self.colors = self.colormap.getLookupTable(0,1,self.n_colors)
        #+ 4 styles de pinceaux, soit 4*n_colors combinaisons
        self.penStyle = [QtCore.Qt.PenStyle.SolidLine,
                        QtCore.Qt.PenStyle.DashLine,
                        QtCore.Qt.PenStyle.DotLine,
                        QtCore.Qt.PenStyle.DashDotLine]

    @property
    def signalsCount (self)-> int:
        return len(self.signals)

    def set_offset(self,time):
        if time is not None:
            if  time != self.offset:
                self.offset = time
                if isinstance(self.data.index, pd.MultiIndex):
                    #on retire l'index time existant
                    self.data = self.data.reset_index(level = 1,drop = True)
                #ajout d'une colonne Time / pas besoin de l'insérer en tête de la dataFrame
                #comme dans les versions précédentes
                self.data['Time'] = np.linspace(self.offset,
                                                self.offset+(self.n_samples-1)*self.sampling,
                                                self.n_samples)
                #on définit la nouvelle colonne time comme deuxième index
                self.data = self.data.set_index('Time',append = True)

    @property
    def display_name(self):
        """Le signal a-t-il subit une modification"""
        return self.name + (" *" if self.offset!=0 or self.start_x!=0 or self.stop_x!=0 else "")

    def get_params(self)-> dict:
        """Récupère l'ensemble des paramètres du signal sous forme de dictionnaire clé-valeur,
        à partir de la structure définie dans opts_dict."""

        return {key:getattr(self, key) for param_path,key in self.opts_dict.items()}

    def get_param(self,key):
        """Récupère la valeur d'un paramètre à partir de sa clé."""
        return getattr(self, key)

    def set_params(self,newParams):
        """Met à jour les paramètres du signal à partir d'un groupe de paramètres."""
        '''_params = custom_struct_functions.extract_parameter_values(   self.PARAMETER_SCHEMA,
                                                                    newParams)'''

        for key, value in newParams.items():
            if key == "offset":
                self.set_offset(value)
            else:
                setattr(self, key, value)

    def add_signal(self, name: str):
        """Ajoute un signal brut ou calculé."""
        pen=self.getDefaultPen()
        sig = SignalObject(self, name,pen)
        self.signals.append(sig)
        return sig

    def get_Y_from_X_index(self,index:int):
        """
        Méthode ne retourant que toutes les valeur en ordonnées des signaux passés par index.
        Args:
            index (int): index des channels devant être récupérés
        Returns:
            pandas.dataframe: données
        """

        if index>=self.n_samples:
            return None
        else:
            try:
                return self.data.iloc[index,:]
            except:
                print(f'{self.name} getYValues(): {index} / {self.n_samples}')

    def getDefaultPen(self,index:int=None):
        """ Méthode retournant le pinceau (couleur+type de trace) du signal en fonction de
            l'index qui lui ai passé

        Args:
            index (int): index de la courbe

        Returns:
            {pg.mkPen}: pen/pinceau de la courbe
        """
        if index is None:
            index = self.signalsCount

        if index >= self.n_colors:
            id_style = index // self.n_colors
            id_color = index % self.n_colors
        else:
            id_style = 0
            id_color = index
        return pg.mkPen(color=self.colors[id_color], style= self.penStyle[id_style])

    def to_dict(self):

        obj_params=self.get_file_loader_params()
        arg_to_export= ['signals']
        obj_params.update({k: v for k, v in self.__dict__.items() if k in arg_to_export })
        obj_params['signals'] = [sig.to_dict() for sig in obj_params['signals']]

        return obj_params
    
    def get_file_loader_params(self):
        
        arg_to_export= ['file_type','import_params','address']
        obj_params = {k: v for k, v in self.__dict__.items() if k in arg_to_export }
        
        return obj_params

    def resolve_filter_references(self):
            """
            Résout toutes les références différées (ex: DiffFilter)
            après que tous les SignalObject ont été recréés.
            """
            # les analyses diff_external font référence à des signaux qui n'appartiennent pas
            # au même fileOBject, c'est donc à la fin du chargement de tout le workspace
            # qu'on peut résoudre ces références
            signal_map = { sig.name: sig   for sig in self.signals }
            for sig in self.signals:
                for filt in sig.pipeline:
                    if filt.action_type.name == "DIFF":
                        filt.resolve_reference(signal_map)


    def signals_from_dict(self,data, filter_factory,analyses_factory):

        for sig_data in data["signals"]:
            sig = SignalObject.from_dict(self, sig_data, filter_factory,analyses_factory)
            self.signals.append(sig)
        self.resolve_filter_references()

    def get_raw_y(self,name):
        """Vraies données brutes."""
        return np.array(self.data[name].values.tolist())

    def get_raw_x(self):
        """Vraies données brutes."""
        return np.array(self.data.index.get_level_values(1).values.tolist())

class SignalObject:
    """
    Représente un signal, dont les données sont calculées dynamiquement
    grâce à un pipeline de filtres non destructif.
    """
    item_type = itemType.RAW
    PARAMETER_SCHEMA= {
                        'Curve name'    :{
                                            'type':'str',
                                            'default':None,
                                            "readonly": True,
                                            "key": "name"
                                        },
                        'Curve unit'    :{
                                            'type':'str',
                                            'default':"°C",
                                            "readonly": False,
                                            "key": "unit"
                                        },
                        'Curve Filters' :{
                                            'type': 'group',
                                            'expanded':True,
                                            'children':
                                                    {
                                                    'Filter curve':{
                                                                    'type':'action',
                                                                    "key": "filter_curve"
                                                                    },
                                                    'Cut-off frequency':{
                                                                        'type':'float',
                                                                        'limits':[0.00001,None],
                                                                        "readonly": False,
                                                                        "key": "cut_off_freq"
                                                                        },
                                                    }
                                        },
                        'Curve pen'     : {
                                            'type':'pen',
                                            'expanded':True,
                                            "readonly": False,
                                            "key": "pen"
                                            }
                    }

    def __init__(self,  file_obj: FileObject,  name: str, pen:pg.mkPen = None ):
        self.file = file_obj
        self.name = name
        # propriétés graphiques
        self.visible = True
        self.is_selected = False
        self.is_reference = False
        self.unit ='°C'
        self.pen = pen
        self.opts_dict = custom_struct_functions.generate_opts_dict(self.PARAMETER_SCHEMA)
        self.cut_off_freq=0.005
        self.filter_curve=False
        # pipeline de filtres : liste de FilterNode
        self.pipeline = []

        # liste des analyses
        self.analyses = []

        # liste des modèles/signaux dérivés
        self.derived_signals = []

        # cache interne
        self._cache = None
        self._cache_valid = False

    # ---------------- BASIC RAW ACCESS ----------------

    @property
    def x(self):
        """Axe des abscisses (colonne 0 du DataFrame)."""
        return self.file.get_raw_x()

    @property
    def is_modified(self):
        """Le signal a-t-il subit une modification"""
        return len(self.pipeline)>0

    @property
    def display_name(self):
        """Le signal a-t-il subit une modification"""
        return self.name + (" *" if self.is_modified else "")

    @property
    def raw_y(self):
        """Vraies données brutes."""
        return self.file.get_raw_y(self.name)

    # ---------------- PIPELINE COMPUTATION ----------------
    def compute(self):
        """Calcule y en appliquant chaque filtre dans l’ordre."""
        if self._cache_valid:
            return self._cache

        y = self.raw_y.copy()
        if self.pipeline:
            for node in self.pipeline:
                y = node.apply(self.x, y)

        self._cache = y
        self._cache_valid = True
        return y

    @property
    def y(self):
        """Accès direct aux données calculées."""
        return np.array(self.compute())

    def invalidate(self):
        """À appeler lorsqu'un filtre est modifié, ajouté ou supprimé."""
        self._cache_valid = False

    def get_params(self):
        """Récupère l'ensemble des paramètres du signal sous forme de dictionnaire clé-valeur,
        à partir de la structure définie dans opts_dict."""

        return {key:getattr(self, key) for param_path,key in self.opts_dict.items()}

    def get_param(self,key):
        """Récupère la valeur d'un paramètre à partir de sa clé."""
        return getattr(self, key)

    def set_params(self,newParams):
        """Met à jour les paramètres du signal à partir d'un groupe de paramètres."""
        '''_params = custom_struct_functions.extract_parameter_values(   self.PARAMETER_SCHEMA,
                                                                    newParams)'''

        for key, value in newParams.items():
            print(f"Setting {key} to {value}")
            setattr(self, key, value)


    def to_dict(self):

        arg_to_export= ['name','visible','pen','pipeline','analyses','is_reference']
        obj_params = {k: v for k, v in self.__dict__.items() if k in arg_to_export }
        obj_params['pipeline']=[node.to_dict() for node in obj_params['pipeline']]
        obj_params['analyses']=[node.to_dict() for node in obj_params['analyses']]
        obj_params['pen']=custom_struct_functions.QPen_to_dict(self.pen)

        return obj_params

    @staticmethod
    def from_dict(file_obj, data, filter_factory,analysis_factory):


        sig             =   SignalObject(file_obj, data["name"])
        sig.visible     =   data.get("visible", True)
        sig.pen         =   custom_struct_functions.dict_to_QPen( data.get("pen"))

        for node_data in data.get("pipeline", []):
            node = filter_factory.create(node_data)
            sig.pipeline.append(node)
        for node_data in data.get("analyses", []):
            node = analysis_factory.create(node_data)
            sig.analyses.append(node)
        return sig


class DerivedSignalObject(SignalObject):
    """
    Signal dérivé (modèle, projection, calcul analytique).
    Contrairement à SignalObject, x et y sont stockés directement.
    """
    item_type = itemType.DERIVED
    PARAMETER_SCHEMA = {
                        'Curve name'    :{
                                            'type':'str',
                                            'default':None,
                                            "readonly": True,
                                            "key": "name"
                                        },
                        'Curve pen'     : {
                                            'type':'pen',
                                            'expanded':True,
                                            "readonly": False,
                                            "key": "pen"
                                            }
                    }

    def __init__(  self,
                    parent_signal: SignalObject,
                    name: str,
                    x: np.ndarray,
                    y: np.ndarray,
                    pen: pg.mkPen = None,
                    metadata: dict | None = None,
                ):
        # On NE passe PAS de FileObject
        self.file = parent_signal.file      # uniquement pour cohérence visuelle / hiérarchie
        self.parent_signal = parent_signal
        self.opts_dict = custom_struct_functions.generate_opts_dict(self.PARAMETER_SCHEMA)
        self.name = name
        self._x = np.asarray(x)
        self._y = np.asarray(y)

        self.visible = True
        self.is_selected = False
        self.is_reference = False

        self.pen = pen

        # Pas de pipeline pour un modèle
        self.pipeline = []
        # Pas d’analyses imbriquées
        self.analyses = []
        self.derived_signals = []

        self.metadata = metadata or {}

        # Pas de cache dynamique
        self._cache = None
        self._cache_valid = True

    @property
    def x(self):
        """Abscisses du signal modèle."""
        return self._x

    @property
    def y(self):
        """Ordonnées du signal modèle."""
        return self._y

    def compute(self):
        return self._y

    def invalidate(self):
        pass


class Workspace:

    def __init__(self):
        self.files = []  # list[FileObject]
        self.reference_signal = None

    def add_file(self, file_obj):
        self.files.append(file_obj)

    def set_reference_signal(self, signal : SignalObject):
        # désactiver l’ancienne référence
        if self.reference_signal is not None:
            self.reference_signal.is_reference = False

        self.reference_signal = signal

        if signal is not None:
            signal.is_reference = True

    def to_dict(self):
        return {
                "version": "1.0",
                "workspace": {
                            "files": [f.to_dict() for f in self.files]
                            }
                }


    def save(self, path):
        with open(path, "w", encoding="utf-8") as f:
            export=self.to_dict()
            json.dump(export, f, indent=2)

    @staticmethod
    def load(path, filter_factory):

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        ws = Workspace()
        file_names=[]
        for file_data in data["workspace"]["files"]:

            file_obj = FileObject.from_dict(file_data, filter_factory)
            ws.add_file(file_obj)
            file_names.append(file_obj.name)

        # Après avoir créé tous les FileObject et SignalObject,
        # on peut résoudre les références différées (ex: diff_external)
        for file_obj in ws.files:
            for sig in file_obj.signals:
                for analysis in sig.analyses:
                    if analysis.action_type.name == "DIFF_EXT":
                        ref_file =  [   file for file in ws.files if
                                        file.name == analysis.params['reference_file']][0]
                        analysis.resolve_reference({s.name: s for s in ref_file.signals})

        return ws


@dataclass(frozen=True)
class SelectionContext:
    role:               itemType
    signal:             SignalObject
    filter_index:       Optional[int] = None
    analysis_index:     Optional[int] = None
    derived_index:      Optional[int] = None
    item:               Optional[TreeItem] = None