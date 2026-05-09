# controller/menu_controller.py

import os,json
from PyQt6 import QtCore, QtGui
from PyQt6.QtWidgets import QMenu,QMenuBar,QMainWindow
import pyqtgraph as pg

from model.base_objects import SignalObject
from ressources import custom_types,custom_dialogs,custom_struct_functions

class MenuController(QtCore.QObject):
    """
    Gère l'affichage du Menu dynamique :
    - MAJ des dossiers récents
    """

    loadSignal = QtCore.pyqtSignal(dict)
    newOptions = QtCore.pyqtSignal(dict)

    def __init__(self, view : QMainWindow, schema : dict , app_name : str ='NewApp'):

        super().__init__()
        self.view   = view
        self.schema = schema
        
        user_config_dir = os.path.expanduser("~") + "/"+app_name
        user_config = user_config_dir + "/settings.json"
        if not os.path.exists(user_config):
            os.makedirs(user_config_dir, exist_ok=True)
            with open(user_config, "w") as f:
                json.dump({"files": []}, f)

        with open(user_config, "r") as f:
            data = json.load(f)
            
        params = data.get("settings",{})
        
        if params:
            self.params = self._deserialize_dict(params)
        else:
            #!defaut params!
            self.params = {}
            
        self.user_config=user_config

        self.update_recent_files_menu()


    def update_recent_files_menu(self):

        #RAZ du sub-menu recent_files_menu
        self.view.recent_files_menu.clear()
        
        #on sort de la fonction si la config utilisateur n'existe pas 
        if not os.path.exists(self.user_config):
            self.view.recent_files_menu.setEnabled(False)
            return
        
        self.view.recent_files_menu.setEnabled(True)
        
        #chargement du JSON à jour 
        with open(self.user_config, "r") as f:
            data = json.load(f)
            
        #création de la liste de fichier: line = [type de fichier, adresse]
        lines = data.get("files", [])
        
        if not lines:
            self.view.recent_files_menu.addAction("No recent files").setEnabled(False)
            return
        
        #lines n'est pas vide, on récupère l'ensemble des données 
        path=lines[0]["address"]
        latest_dir=path[:path.rindex('/')]
        self.view.latest_dir=latest_dir
        for loader in lines:
            
            if (loader["file_type"] not in custom_types.fileType.__members__
                or not loader["address"]):
                continue
            action = QtGui.QAction(loader["address"], self)
            action.setData(loader)
            action.triggered.connect(self._on_recent_file_triggered)
            self.view.recent_files_menu.addAction(action)

    def _on_recent_file_triggered(self):
        action = self.sender()
        loader_struct = action.data()
        self.loadSignal.emit(loader_struct)

    def save_recent_file_address(self, new_loader):
        if not os.path.exists(self.user_config):
            with open(self.user_config, "w") as f:
                json.dump({"files": []}, f)
        with open(self.user_config, "r") as f:
            data = json.load(f)
        file_loaders = data.get("files", [])
        #si l'adresse existe déjà dans la liste on la retire
        index=None
        for n,loader_struct in enumerate(file_loaders):
            if new_loader["address"] == loader_struct["address"]:
                index=n
                break
        if index is not None:
            file_loaders.pop(index)

        #on ne garde que les 10 fichiers les plus récents
        file_loaders.insert(0,new_loader)
        file_loaders = file_loaders[:10]
        with open(self.user_config, "w") as f:
            data["files"]=file_loaders
            json.dump(data, f, indent=4)
        self.update_recent_files_menu()


    def open_options_window(self,settings=None):
        """
        Méthode gérant l'éxécution de la fenêtre de dialogue regroupant
        les options du GLViewer
        """
        if settings is None or not settings:
            settings = self.params
            
        OptionsWindow = custom_dialogs.OptionsPannel(schema = self.schema,
                                                    saved_options = settings, 
                                                    parent = self.view)
        OptionsWindow.accepted.connect(lambda: self.get_new_settings(
                                                    OptionsWindow.getOptions()))
        OptionsWindow.show()
        
    def get_new_settings(self,options):
        
        self.newOptions.emit(options)
        self.params.update(options)
        self.save_options_to_file(self._serialize_dict(options),self.user_config)
        
    def _serialize_dict(self,options):
        
        serialized_option={}
        for k,val in options.items():
            if isinstance(val,QtGui.QColor):
                serialized_option[k]=custom_struct_functions.QColor_to_dict(val)
            else:
                serialized_option[k]=val
        return serialized_option
    
    def _deserialize_dict(self,options):
        
        deserialized_option={}
        for key,val in options.items():
            if key == 'background_color':
                deserialized_option[key]=custom_struct_functions.dict_to_QColor(val)
            else:
                deserialized_option[key]=val
        return deserialized_option

    @staticmethod
    def save_options_to_file(options: dict, filepath):
        if os.path.exists(filepath):
            with open(filepath, "r") as f:
                data = json.load(f)
                data["settings"]=options
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)


