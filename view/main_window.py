
# view/main_window.py

from PyQt6 import uic
from PyQt6 import QtWidgets,QtGui,QtCore
from ressources import theme

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
        # enregistrement du projet ouvert (Ctrl+S) ; « Save to » devient « Save as »
        self.actionSave = QtGui.QAction("Save", self)
        self.actionSave.setShortcut(QtGui.QKeySequence.StandardKey.Save)
        self.menuFiles.insertAction(self.actionSave_to, self.actionSave)
        self.actionSave_to.setText("Save as...")
        self.actionSave_to.setShortcut(QtGui.QKeySequence.StandardKey.SaveAs)
        # fermeture de la fenêtre : callable() -> bool, False pour l'annuler (travail non
        # enregistré, voir MainController.confirm_discard)
        self.close_guard = None
        # comparaison des essais (modèles thermiques) : fenêtre à part
        self.actionBenchmark = QtGui.QAction("Benchmark window", self)
        self.menuOptions.addAction(self.actionBenchmark)
        self._init_toolbar()
        self.default_dir=os.path.dirname(__file__)
        #lastest_dir sera mis à jour 
        self.latest_dir=os.path.dirname(__file__)

    def _init_toolbar(self):
        """
        Barre d'outils : raccourcis vers les actions les plus utilisées des menus (mêmes
        QAction, donc même comportement). Undo / Redo : voir add_history_actions.
        """
        self.toolbar = QtWidgets.QToolBar("Barre d'outils", self)
        self.toolbar.setObjectName("main_toolbar")
        self.toolbar.setMovable(False)
        self.toolbar.setFloatable(False)
        self.toolbar.setIconSize(QtCore.QSize(20, 20))
        self.toolbar.toggleViewAction().setEnabled(False)   # pas de masquage par clic droit
        self.addToolBar(QtCore.Qt.ToolBarArea.TopToolBarArea, self.toolbar)
        for action, icon_name, tip in (
                (self.actionLoad_json,          "open",     "Ouvrir un projet (.json)"),
                (self.actionSave,               "save",     "Enregistrer le projet (Ctrl+S)"),
                (None, None, None),
                (self.actionLoad_csv,           "graphtec", "Charger un fichier Graphtec (.csv)"),
                (self.actionGeneric_csv_file,   "import",   "Importer un fichier .csv"),
                (None, None, None),
                (self.actionBenchmark,          "benchmark","Fenêtre Benchmark"),
                (self.actionParameters,         "settings", "Paramètres")):
            if action is None:
                self.toolbar.addSeparator()
                continue
            theme.set_action_icon(action, icon_name)
            action.setToolTip(tip)
            self.toolbar.addAction(action)
        # emplacement d'Undo / Redo (créées par le contrôleur) : après « Enregistrer »
        self._history_anchor = self.toolbar.actions()[2]

    def add_history_actions(self, undo: QtGui.QAction, redo: QtGui.QAction):
        """
        Undo / Redo dans la barre d'outils, après le groupe Ouvrir / Enregistrer (leur
        info-bulle reprend le texte de l'action : « Undo <dernière action> »).
        """
        theme.set_action_icon(undo, "undo")
        theme.set_action_icon(redo, "redo")
        self.toolbar.insertActions(self._history_anchor, [undo, redo])
        self.toolbar.insertSeparator(undo)

    def closeEvent(self, event):
        if self.close_guard is not None and not self.close_guard():
            event.ignore()
            return
        super().closeEvent(event)

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