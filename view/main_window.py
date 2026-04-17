
# view/main_window.py

from PyQt6 import uic
from PyQt6 import QtWidgets,QtGui

import pathlib,os,json

PATH=pathlib.Path(__file__).parent

class MainWindow(QtWidgets.QMainWindow):
    """
    Fenêtre principale qui charge ton fichier .ui et expose les widgets principaux
    pour que les controllers s'y connectent.
    """

    def __init__(self,**opts):
        super().__init__()
        uic.loadUi(PATH/"MainWindow2.ui", self)
        self.setWindowIcon(QtGui.QIcon(str(PATH)+'/icon.ico'))
        self.treefile : QtWidgets.QTreeView
        self.default_dir=os.path.dirname(__file__)
        #lastest_dir sera mis à jour 
        self.latest_dir=os.path.dirname(__file__)

    def _initialise_splitter(self):
        
        self.splitter.setStretchFactor(0, 7)
        self.splitter.setStretchFactor(1, 1)
        self.splitter_2.setStretchFactor(0, 3)
        self.splitter_2.setStretchFactor(1, 2)
        self.splitter_3.setStretchFactor(0, 5)
        self.splitter_3.setStretchFactor(1, 3)