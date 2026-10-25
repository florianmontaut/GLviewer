
# model/base_objects.py

from PyQt6 import QtCore, QtGui
from collections import OrderedDict

import numpy as np
import pandas as pd
import json



import pyqtgraph as pg
import pyqtgraph.parametertree as ptree


from ressources import custom_parameters,custom_struct_functions
from ressources.custom_items import itemType,FileStruct
from model.tree_item import TreeItem


import uuid



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
                        # point de fonctionnement de l'essai (ex: « 100 W / 55 °C »)
                        'Label'        :{
                                            'type':'str',
                                            'default':"",
                                            "readonly": False,
                                            "key": "label"
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
        self.id = uuid.uuid4().hex

        self.label = getattr(self, "label", "")    # point de fonctionnement de l'essai
        # fichier retiré de l'espace de travail (conservé pour l'undo)
        self.removed = False
        self.signals = []   # Liste de SignalObject
        self._raw_x = None  # cache de l'axe des temps (voir get_raw_x)
        self._window = None # cache de la fenêtre de troncature (voir window)
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
                self._raw_x = None
                self._window = None
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
                if key in ("start_x", "stop_x"):
                    self._window = None

    # ---------------- troncature (calque appliqué en entrée du pipeline) ----------------

    def window(self) -> slice:
        """
        Échantillons conservés après troncature : Truncate left (start_x) masque les
        start_x premières secondes de l'enregistrement, Truncate right (stop_x) les stop_x
        dernières. Les données brutes ne sont pas modifiées ; au moins 2 échantillons
        sont conservés.
        """
        if self._window is None:
            x = self.get_raw_x()
            start = int(np.searchsorted(x, x[0] + max(0.0, self.start_x or 0.0), side="left"))
            stop = int(np.searchsorted(x, x[-1] - max(0.0, self.stop_x or 0.0), side="right"))
            if stop - start < 2:
                # troncatures plus longues que l'enregistrement : rien n'est masqué
                start, stop = 0, len(x)
            self._window = slice(start, stop)
        return self._window

    def get_x(self):
        """
        Axe des temps après troncature (vue en lecture seule de l'axe brut). Mis en cache :
        les signaux comparent l'identité de cet axe pour valider leur cache de pipeline.
        """
        raw, win = self.get_raw_x(), self.window()
        key = (id(raw), win.start, win.stop)
        if getattr(self, "_x_window_key", None) != key:
            self._x_window = raw[win]
            self._x_window_key = key
        return self._x_window

    def get_y(self, name):
        """Valeurs brutes d'une voie après troncature (copie)."""
        return self.get_raw_y(name)[self.window()]

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
        
        # paramètres du fichier (ParameterTree) : décalage temporel et troncatures
        arg_to_export= ['file_type','import_params','address','offset','start_x','stop_x',
                        'label']
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
                for filter in sig.pipeline.values(): #! orderedDict
                    if filter.action_type.name == "DIFF":
                        filter.resolve_reference(signal_map)


    def signals_from_dict(self,data, filter_factory,analyses_factory):

        for sig_data in data["signals"]:
            sig = SignalObject.from_dict(self, sig_data, filter_factory,analyses_factory)
            self.signals.append(sig)
        self.resolve_filter_references()

    def channel_id(self, name) -> str | None:
        """
        Numéro de la voie d'acquisition : celui du GL (« CH3 », relevé à l'import ; les
        numéros ne se suivent pas forcément), sinon la position de la colonne (« CH1 »
        pour la première voie d'un .csv / .txt).
        """
        params = self.import_params if isinstance(self.import_params, dict) else {}
        ids = params.get('channel_ids') or {}
        if name in ids:
            return ids[name]
        columns = list(self.data.columns)
        return f"CH{columns.index(name) + 1}" if name in columns else None

    def get_raw_y(self,name):
        """Vraies données brutes (copie)."""
        return self.data[name].to_numpy(dtype=float, copy=True)

    def get_raw_x(self):
        """
        Axe des temps, commun à tous les signaux du fichier. Mis en cache (recalculé après
        un changement de décalage, voir set_offset) et en lecture seule : sig.x est lu à
        chaque mise à jour du graphique, des limites de zoom... (1 million de points pour
        un .txt de NTC à 1 Hz).
        """
        if self._raw_x is None:
            x = self.data.index.get_level_values(1).to_numpy(dtype=float, copy=True)
            x.setflags(write=False)
            self._raw_x = x
        return self._raw_x

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
        self.id = uuid.uuid4().hex
        
        self.pipeline = OrderedDict() # filter_id -> FilterNode
        self.analyses = OrderedDict() # analysis_id -> AnalysisNode
        self.pipeline_version = 0
        # liste des modèles/signaux dérivés
        self.derived_signals = []

        # cache interne : y et x calculés par le pipeline
        self._cache = None
        self._x_cache = None
        self._cache_raw_x = None   # axe brut ayant servi au calcul du cache
        self._cache_valid = False
        self._cache_version = None # pipeline_version ayant servi au calcul du cache

    # ---------------- BASIC RAW ACCESS ----------------

    @property
    def channel_id(self) -> str | None:
        """Numéro de la voie d'acquisition (ex: « CH3 », voir FileObject.channel_id)."""
        return self.file.channel_id(self.name)

    @property
    def x(self):
        """
        Axe des temps calculé par le pipeline (ex: décalage temporel), en lecture seule.
        Sans filtre, c'est l'axe des temps brut du fichier.
        """
        if not self.pipeline:
            return self.file.get_x()
        self.compute()
        return self._x_cache

    @property
    def raw_x(self):
        """Axe des temps brut du fichier (commun aux voies, en lecture seule)."""
        return self.file.get_raw_x()

    def time_shift(self) -> float:
        """
        Décalage entre l'axe des temps affiché (décalage du fichier, filtres « X offset »)
        et le temps de l'enregistrement (secondes depuis le début du fichier, sans
        décalage). Une plage exprimée en temps de l'enregistrement reste sur les mêmes
        échantillons quand le signal est décalé.
        """
        x = self.x
        if len(x) == 0:
            return 0.0
        record_time = self.file.get_raw_x()[self.file.window().start] - self.file.offset
        return float(x[0] - record_time)

    def input_key(self) -> tuple:
        """
        État des données du signal : pipeline (filtres, undo/redo) et fenêtre du fichier
        (décalage, troncatures). Sert à détecter les signaux dérivés périmés.
        """
        window = self.file.window()
        return (self.pipeline_version, self.file.offset, window.start, window.stop)

    def refresh_derived(self) -> tuple[list, list]:
        """
        Recalcule les signaux dérivés des analyses dont les données d'entrée ont changé
        depuis leur calcul (filtre ajouté, décalage du fichier, référence modifiée...).
        Une analyse dont le recalcul échoue perd son signal dérivé (courbe périmée
        retirée) et garde la raison dans analysis.error ; elle est retentée quand ses
        données d'entrée changent à nouveau.

        Returns:
            (analyses recalculées ou en échec, messages d'échec)
        """
        changed, errors = [], []
        for analysis in self.analyses.values():
            key = analysis.input_key(self)
            current = [ds for ds in self.derived_signals
                       if ds.metadata.get('analysis_id') == analysis.id]
            if current and all(ds.metadata.get('input_key') == key for ds in current):
                continue
            if not current and analysis.error is not None and analysis._error_key == key:
                continue                        # déjà en échec avec ces données
            for ds in current:
                self.derived_signals.remove(ds)
            try:
                self.derived_signals.append(analysis.derive(self))
                analysis.error = None
            except Exception as e:
                analysis.error = str(e)
                analysis._error_key = key
                errors.append(f"{self.name} / {analysis.display_name} : {e}")
            changed.append(analysis)
        return changed, errors

    def nearest_value(self, x: float):
        """
        Valeur (après filtres) de l'échantillon le plus proche de l'instant x, ou None.
        Recherche dichotomique : l'axe des temps est croissant.
        """
        xs = self.x
        if len(xs) == 0:
            return None
        ys = self.compute()
        i = int(np.searchsorted(xs, x))
        if i >= len(xs):
            i = len(xs) - 1
        elif i > 0 and abs(xs[i-1] - x) <= abs(xs[i] - x):
            i -= 1
        return float(ys[i])

    @property
    def is_modified(self):
        """Le signal a-t-il subit une modification"""
        return len(self.pipeline.values())>0 #! orderedDict

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
        """
        Calcule y (et l'axe des temps) en appliquant chaque filtre dans l'ordre, comme des
        calques : chaque filtre reçoit le x et le y produits par les filtres précédents et
        retourne de nouveaux tableaux. Les données brutes du fichier ne sont jamais modifiées.
        """
        # toute modification du pipeline incrémente pipeline_version (voir commandes) ;
        # l'axe brut change avec le décalage temporel du fichier (FileObject.set_offset)
        # point de départ : données brutes du fichier, fenêtre de troncature appliquée
        raw_x = self.file.get_x()
        if (self._cache_valid and self._cache_version == self.pipeline_version
                and self._cache_raw_x is raw_x):
            return self._cache

        x = raw_x
        y = self.file.get_y(self.name)
        for node in self.pipeline.values(): #! orderedDict
            y = node.apply(x, y)
            x = node.apply_x(x)
        if x.flags.writeable:
            x.setflags(write=False)

        self._cache = y
        self._x_cache = x
        self._cache_raw_x = raw_x
        self._cache_valid = True
        self._cache_version = self.pipeline_version
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
            #print(f"Setting {key} to {value}")
            setattr(self, key, value)

    #### Helpers de recherche par ID et index ####
    '''
    def get_filter_by_id(self, filter_id):
        return self.pipeline.get(filter_id)

    def get_analysis_by_id(self, analysis_id):
        return self.analyses.get(analysis_id)

    def _get_filter_index(self, filter_id):
        return list(self.pipeline.keys()).index(filter_id)

    def _get_analysis_index(self, analysis_id):
        return list(self.analyses.keys()).index(analysis_id)

    def get_node_index(self, filter_id = None, analysis_id = None):
        if filter_id is None:
            return self._get_analysis_index(analysis_id)
        else:
            return self._get_filter_index(filter_id)
        
    def _get_filter_by_index(self, index):
        return list(self.pipeline.values())[index]

    def _get_analysis_by_index(self, index):
        return list(self.analyses.values())[index]
    
    def get_node_by_index(self, filter_index = None, analysis_index = None):
        if filter_index is None:
            return self._get_analysis_by_index(analysis_index)
        else:
            return self._get_filter_by_index(filter_index)
    '''
    
# ------------------------------------------------------------------
    # Filters
    # ------------------------------------------------------------------

    def get_filter_by_id(self, filter_id):
        if filter_id is None:
            return None
        return self.pipeline.get(filter_id)

    def get_filter_index_by_id(self, filter_id):
        if filter_id is None:
            return None

        try:
            return list(self.pipeline.keys()).index(filter_id)
        except ValueError:
            return None

    def get_filter_by_index(self, index):
        if index is None:
            return None

        values = list(self.pipeline.values())

        if index < 0 or index >= len(values):
            return None

        return values[index]

    def get_filter_id_by_index(self, index):
        if index is None:
            return None

        keys = list(self.pipeline.keys())

        if index < 0 or index >= len(keys):
            return None

        return keys[index]

    # ------------------------------------------------------------------
    # Analyses
    # ------------------------------------------------------------------

    def get_analysis_by_id(self, analysis_id):
        if analysis_id is None:
            return None
        return self.analyses.get(analysis_id)

    def get_analysis_index_by_id(self, analysis_id):
        if analysis_id is None:
            return None

        try:
            return list(self.analyses.keys()).index(analysis_id)
        except ValueError:
            return None

    def get_analysis_by_index(self, index):
        if index is None:
            return None

        values = list(self.analyses.values())

        if index < 0 or index >= len(values):
            return None

        return values[index]

    def get_analysis_id_by_index(self, index):
        if index is None:
            return None

        keys = list(self.analyses.keys())

        if index < 0 or index >= len(keys):
            return None

        return keys[index]



    #### Helpers de recherche par ID et index ####


    def to_dict(self):

        arg_to_export= ['name','visible','pen','pipeline','analyses','is_reference']
        obj_params = {k: v for k, v in self.__dict__.items() if k in arg_to_export }
        obj_params['pipeline'] = [(n_id,node.to_dict()) for n_id,node in
                                    obj_params['pipeline'].items()] 
        obj_params['analyses'] = [(n_id,node.to_dict()) for n_id,node in 
                                    obj_params['analyses'].items()] 
        obj_params['pen']=custom_struct_functions.QPen_to_dict(self.pen)

        return obj_params

    @staticmethod
    def from_dict(file_obj, data, filter_factory,analysis_factory):


        sig             =   SignalObject(file_obj, data["name"])
        sig.visible     =   data.get("visible", True)
        sig.pen         =   custom_struct_functions.dict_to_QPen( data.get("pen"))

        #! Ordered dict n'est pas sérialisable ! => liste de [id, node_dict]
        # l'id sauvegardé est réattribué au node : clé du dict et node.id doivent coïncider
        for entry in data.get("pipeline", []):
            node_id, node_data = SignalObject._split_saved_node(entry)
            node = filter_factory.create(node_data)
            node.id = node_id or node.id
            sig.pipeline[node.id]=node
        for entry in data.get("analyses", []):
            node_id, node_data = SignalObject._split_saved_node(entry)
            if not node_data:
                # anciens projets : une analyse thermique sans résultat était sauvée {}
                continue
            node = analysis_factory.create_saved(node_data)
            node.id = node_id or node.id
            sig.analyses[node.id]=node
        return sig

    @staticmethod
    def _split_saved_node(entry):
        """
        Format actuel : [id, {"type":..., "params":...}]
        Ancien format (projets d'avant les ID) : {"type":..., "params":...}, sans id
        """
        if isinstance(entry, dict):
            return None, entry
        node_id, node_data = entry
        return node_id, node_data


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
        self.pipeline = OrderedDict() #! orderedDict
        # Pas d’analyses imbriquées 
        self.analyses = OrderedDict() #! orderedDict
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
        # vue « Par voie » : mode d'appariement des voies entre fichiers ("name" /
        # "channel", None tant que l'utilisateur n'a pas choisi) et associations faites à
        # la main, par mode : {mode: {SignalObject: clé de la voie logique}}
        self.channel_matching = None
        self.channel_links = {"name": {}, "channel": {}}
        # groupes de voies logiques créés par l'utilisateur (model.channels.UserGroup)
        self.channel_groups = []
        # fichier projet .json (ouvert ou enregistré), None si jamais enregistré
        self.path = None
        # textes ajoutés sur le graphique : id -> TextAnnotation
        self.annotations = OrderedDict()

    def add_file(self, file_obj):
        self.files.append(file_obj)
        # formules : voies des autres fichiers ([200 W:T AMB], voir FormulaAnalysis)
        file_obj.workspace = self

    def set_reference_signal(self, signal : SignalObject):
        # désactiver l’ancienne référence
        if self.reference_signal is not None:
            self.reference_signal.is_reference = False

        self.reference_signal = signal

        if signal is not None:
            signal.is_reference = True

    @property
    def matching_mode(self) -> str:
        """Mode d'appariement des voies en vigueur (par nom tant qu'aucun n'est choisi)."""
        return self.channel_matching or "name"

    def channels_to_dict(self) -> dict:
        """Appariement des voies : un signal est repéré par (rang du fichier, nom)."""
        links = []
        for mode, mode_links in self.channel_links.items():
            for sig, key in mode_links.items():
                if sig.file in self.files:
                    links.append({"mode": mode, "file": self.files.index(sig.file),
                                  "signal": sig.name, "key": key})
        return {"matching": self.channel_matching, "links": links,
                "groups": [group.to_dict() for group in self.channel_groups]}

    def channels_from_dict(self, data: dict):
        """Inverse de channels_to_dict (absent des projets plus anciens)."""
        from model.channels import UserGroup
        data = data or {}
        self.channel_matching = data.get("matching")
        self.channel_groups = [UserGroup.from_dict(group) for group in data.get("groups", [])]
        for link in data.get("links", []):
            try:
                file_obj = self.files[link["file"]]
                sig = next(s for s in file_obj.signals if s.name == link["signal"])
            except (IndexError, StopIteration):
                continue
            self.channel_links.setdefault(link["mode"], {})[sig] = link["key"]

    def to_dict(self):
        return {
                "version": "1.0",
                "workspace": {
                            "files": [f.to_dict() for f in self.files],
                            "annotations": [a.to_dict() for a in self.annotations.values()],
                            "channels": self.channels_to_dict(),
                            }
                }


    def recent_file_params(self) -> dict:
        """Entrée du menu « Recent files » pour le projet (voir FileObject.get_file_loader_params)."""
        return {"file_type": "JSON", "address": self.path, "import_params": {}}

    def save(self, path):
        self.path = path
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
                    #! analysis.id = data["id"] <= il faut recharger l'id sauvegardé
                    if analysis.action_type.name == "DIFF_EXT":
                        ref_file =  [   file for file in ws.files if
                                        file.name == analysis.params['reference_file']][0]
                        analysis.resolve_reference({s.name: s for s in ref_file.signals})

        return ws

