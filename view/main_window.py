
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
        self._init_tree_tabs()
        # comparaison des essais (modèles thermiques) : fenêtre à part
        self.actionBenchmark = QtGui.QAction("Benchmark window", self)
        self.menuOptions.addAction(self.actionBenchmark)
        self.default_dir=os.path.dirname(__file__)
        #lastest_dir sera mis à jour 
        self.latest_dir=os.path.dirname(__file__)

    def _init_tree_tabs(self):
        """
        Onglets « Par fichier » (arbre d'origine, treefile) et « Par voie » (treechannels :
        une même voie dans plusieurs fichiers), à la place de treefile dans le splitter.
        """
        splitter = self.treefile.parentWidget()
        position = splitter.indexOf(self.treefile)
        self.tree_tabs = QtWidgets.QTabWidget()
        # mêmes réglages que treefile dans le .ui (largeur minimale, rapport 1 pour 6 avec
        # le graphique) : sinon les onglets s'ouvrent repliés, à 0 pixel de large
        self.tree_tabs.setSizePolicy(self.treefile.sizePolicy())
        self.tree_tabs.setMinimumWidth(max(self.treefile.minimumWidth(), 200))
        splitter.insertWidget(position, self.tree_tabs)
        self.tree_tabs.addTab(self.treefile, "Par fichier")
        self.treechannels = QtWidgets.QTreeView()
        self.treechannels.setAllColumnsShowFocus(True)
        self.tree_tabs.addTab(self.treechannels, "Par voie")
        # l'arborescence ne peut pas être repliée en glissant le séparateur
        splitter.setCollapsible(splitter.indexOf(self.tree_tabs), False)

    def _initialise_splitter(self):
        
        self.splitter.setStretchFactor(0, 7)
        self.splitter.setStretchFactor(1, 1)
        self.splitter_2.setStretchFactor(0, 3)
        self.splitter_2.setStretchFactor(1, 2)
        self.splitter_3.setStretchFactor(0, 5)
        self.splitter_3.setStretchFactor(1, 3)