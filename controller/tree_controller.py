
# controller/tree_controller.py

from PyQt6 import QtCore,QtGui,QtWidgets
from model.base_objects import SignalObject,DerivedSignalObject
from model.filters.base_filter import FilterNode
from model.analysis.base_analysis import AnalysisNode
from PyQt6.QtWidgets import QTreeView

from controller.tree_context_menu_controller import TreeContextMenu
from model.tree_item import TreeItem
from ressources.custom_menu import SelectionState
from ressources import custom_types,custom_items

class TreeController(QtCore.QObject):
    """
    Contrôle le QTreeView :
    - sélection de signal
    - sélection de filtre
    - visibilité (checkbox)
    """
    # (sig, filter_idx, analysis_idx)
    item_selected = QtCore.pyqtSignal(TreeItem,QtCore.QModelIndex) #tuple(SignalObject,int,int)
    visibility_changed = QtCore.pyqtSignal(SignalObject)
    menu_actions_triggered  = QtCore.pyqtSignal(custom_types.ActionModifier,
                                                custom_types.qSignalType,
                                                object)

    def __init__(self, tree: QTreeView):
        super().__init__()

        self.tree = tree  # QTreeView
        self.model = None
        self.macro_recording=False
        self.ref=None
        #self.tree.header().hide()
        self._init_tree_menu()


    # ----------------------------------------------------------
    def set_model(self, model):
        self.model = model
        self.tree.setModel(model)

        selection_model = self.tree.selectionModel()
        header = self.tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Interactive)

        self.tree.setColumnWidth(0, 250)  # Nom du signal
        self.tree.setColumnWidth(1, 100)  # Valeur

        self.expand_items()
        self.tree.viewport().update()
        selection_model.selectionChanged.connect(self._on_selection_changed)
        self.model.dataChanged.connect(self._on_checkbox_changed)

    # ----------------------------------------------------------
    '''
    def _resolve_signal_node_index(self, item):
        """Retourne l'index métier d'un nœud Filter/Analysis pour le Signal associé."""
        obj = item.data
        if item.role == custom_items.itemType.FILTER:
            sig = item.parent.data
            try:
                return (None, sig, sig.pipeline.index(obj), None)
            except ValueError:
                return (None, sig, None, None)

        if item.role == custom_items.itemType.ANALYSE:
            sig = item.parent.data
            print(f"Signal associé à l'analyse : {sig.display_name} / nombre d'analyses : {len(sig.analyses)}")
            try:
                return (None, sig, None, sig.analyses.index(obj))
            except ValueError as e:
                print(f"Erreur lors de la recherche de l'analyse : {e}")
                return (None, sig, None, None)

        if item.role == custom_items.itemType.RAW:
            return (None, obj, None, None)

        return (obj, None, None, None)
    '''
    def _on_selection_changed(self, selected=None, deselected=None):
        if selected is not None:
            if not selected.indexes():
                return

            index = selected.indexes()[0]
            item = index.internalPointer()
            obj = item.data
            print(  f'Item sélectionné: {obj.display_name} / {type(obj)} /'+
                    f'{isinstance(obj, AnalysisNode)}')

            #result = self._resolve_signal_node_index(item)
            self.item_selected.emit(item,index)
            self.checkStates(obj)
        else:
            self.checkStates()

    def checkStates(self,selected=None):
        if selected is not None:

            #? faut-il vraiment interdire l'accès aux actions si un filtre est sélectionné
            if isinstance(selected,SignalObject|DerivedSignalObject):
                ref = [sig for sig in selected.file.signals if sig.is_reference]
                if ref:
                    ref = ref[0]
                else:
                    ref = None
                has_select=True
                has_ref = ref is not None and not selected.is_reference
            else:
                has_select = False
                has_ref= False
        else:
            has_select = False
            has_ref= False

        states = SelectionState(
                                    has_selection = has_select ,
                                    has_reference = has_ref,
                                    is_recording  = self.macro_recording,
                                    )
        self.menu.update_enabled_states(states)


    def _on_checkbox_changed(self,  topLeft, bottomRight, roles):

        if QtCore.Qt.ItemDataRole.CheckStateRole not in roles:
            return

        #on récupère l'item correspondant à l'index
        #pour récupéère l'objet signalObject, on utilise la méthode '.data'
        index = topLeft
        item = index.internalPointer()
        obj = item.data

        if isinstance(obj, SignalObject):
            self.visibility_changed.emit(obj)


    def _init_tree_menu(self):
        """
        méthode alembiqué mais permet de voir la technique de passage d'information
        via les slots et non pas via signals
        """
        self.menu = TreeContextMenu(
                                        self.tree,
                                        action_callback=self.actions_forwarding
                                    )
        self._on_selection_changed(None,None)


    def actions_forwarding(self, action_type,macro_name=None):
        """
        Route l'action demandée vers la bonne méthode métier
        """

        self.menu_actions_triggered.emit(   custom_types.ActionModifier.ADD_ACTION,
                                            action_type,
                                            macro_name)

    def expand_items(self,index: QtCore.QModelIndex = None):
        """
        Développe tous les items pour afficher les items enfants.
        Si aucun index n'est passé, se contente de développer tous les fileItems
        """

        # niveau 0 = Workspace
        root_index = QtCore.QModelIndex()

        # niveau 1 = FileObject

        for row in range(self.model.rowCount(root_index)):
            if index is None:
                file_index = self.model.index(row, 0, root_index)
                self.tree.expand(file_index)
            else:
                self.tree.expand(self.model.parent(index))
