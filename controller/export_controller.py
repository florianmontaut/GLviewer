import pandas as pd
import numpy as np

from PyQt6 import QtGui,QtCore,QtWidgets

from model.base_objects import FileObject, SignalObject,Workspace

class ExportController(QtCore.QObject):


    def __init__(self,view: QtWidgets.QMainWindow,**opts):
        
        super().__init__()
        self.view = view
        self.workspace = None
        self.optsDict = {
                        ("File import setting","Use latest files as working folder"): "latest_import",
                        ("File import setting","Set working folder")                : "custom_folder"
                        }
        self.opts = {
                        "custom_folder"  :  "",
                        "latest_import"  : True
                    }
        if opts:
            self.updateOptions(**opts)

    
    @property
    def defaultAdress(self):
        if self.opts['latest_import']:
            return self.view.latest_dir
        else:
            if self.opts['custom_folder']:
                return self.opts['custom_folder']
            else:
                return self.view.default_dir
        
    def updateOptions(self,opts):

        self.opts.update({self.optsDict[key]:item for key,item in opts["Import settings"].items()})

    def save_to_json(self,workspace:Workspace):
        
        self.workspace=workspace
        
    def save_workspace(self,workspace:Workspace):
        self.workspace=workspace
        path, _ = QtWidgets.QFileDialog.getSaveFileName(  self.view,
                                                "Save Workspace",
                                                self.defaultAdress,
                                                "Workspace (*.json)"
                                            )
        if path:
            self.workspace.save(path)