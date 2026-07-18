
# controller/tree_controller.py

from PyQt6 import QtCore,QtGui,QtWidgets
from model.base_objects import SignalObject,DerivedSignalObject

from model.tree_item import TreeItem
from model.tree_model import PipelineTreeModel
from PyQt6.QtWidgets import QTreeView

from controller.tree_context_menu_controller import TreeContextMenu

from ressources.custom_menu import SelectionState
from ressources import custom_types
from ressources.custom_items import SelectionContext,itemType

class TreeController(QtCore.QObject):
    """
    Contrôle le QTreeView :
    - sélection de signal
    - sélection de filtre
    - visibilité (checkbox)
    """
    # (sig, filter_idx, analysis_idx)
    item_selected = QtCore.pyqtSignal(SelectionContext) #tuple(SignalObject,int,int)
    visibility_changed = QtCore.pyqtSignal(SignalObject)
    menu_actions_triggered  = QtCore.pyqtSignal(custom_types.ActionModifier,
                                                custom_types.qSignalType,
                                                object)

    def __init__(self, tree: QTreeView):
        super().__init__()

        self.tree = tree  # QTreeView
        self.model : PipelineTreeModel = None
        self.macro_recording=False
        self.reference_sig = None
        #self.tree.header().hide()
        self._init_tree_menu()


    # ----------------------------------------------------------
    def set_model(self, model : PipelineTreeModel):
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
        #selection_model.currentChanged.connect(lambda: print("changed!"))
        self.model.dataChanged.connect(self._on_checkbox_changed)

    #* Nouvelle version 17/07   *#
    def _on_selection_changed(self, selected, deselected):
        if selected is None:
            return
        indexes = selected.indexes()
        if not indexes:
            return
        index = indexes[0]
        item = index.internalPointer()
        obj=item.obj
        obj.is_selected = True
        if item is None:
            return
        ctx = item.to_selection_context()
        if ctx is None:
            return
        if deselected is not None or not deselected:
            indexes = deselected.indexes()
            for index in indexes:
                item: TreeItem = index.internalPointer()
                obj = item.obj
                obj.is_selected = False
        self.item_selected.emit(ctx)
    #* Nouvelle version 17/07   *#
    
    def _build_selection_context(self, item: TreeItem) -> SelectionContext:
        role = item.role
        obj = item.obj


        if role == itemType.FILE:
            return SelectionContext(
                                        role        = role,
                                        signal      = obj,
                                        item        = item
                                    )

        if role == itemType.RAW:
            return SelectionContext(
                                        role        = role,
                                        signal      = obj,
                                        item        = item
                                    )

        if role == itemType.FILTER:
            sig = item.parent_item.obj
            return SelectionContext(
                                        role            = role,
                                        signal          = sig,
                                        filter_id       = obj.id,
                                        item            = item
                                    )

        if role == itemType.ANALYSE:
            sig = item.parent_item.obj
            #! la modification/update du signal ext plante. 02/05
            return SelectionContext(
                                        role                = role,
                                        signal              = sig,
                                        analysis_id         = obj.id,
                                        item                = item
                                    )
        #! Derived est amené à être supprimé
        if role == itemType.DERIVED:
            analysis_item = item.parent_item
            sig_item = analysis_item.parent_item
            sig = sig_item.obj
            return SelectionContext(
                                        role            = role,
                                        signal          = sig,
                                        derived_id      = sig.derived_signals.index(obj),
                                        item            = item
                                    )

        raise RuntimeError(f"Unhandled TreeItem role: {role}")

    
    def _build_selection_context(self, item: TreeItem):
        return item.to_selection_context()


    def find_treeItem(self,sig):

        return self.model.find_item(self.model.root,sig)

    def select_tree_from_context(self, ctx: SelectionContext):
        sel_model   = self.tree.selectionModel()
        sig_item    = self.find_treeItem(ctx.signal)
        if sig_item is None:
            return
        index = None
        # ✅ RAW signal
        if ctx.role == itemType.RAW:
            index = self.model.signal_index_map.get(ctx.signal)

        # ✅ FILTER
        elif ctx.role == itemType.FILTER:
            #index = self.model.index_from_item(ctx.get_node())
            #! risque d'être détruit par l'ajout des dossiers
            node_item = self.model.find_item(sig_item, ctx.get_node())
            index = self.model.index_from_item(node_item)

        # ✅ ANALYSE
        elif ctx.role == itemType.ANALYSE:
            #! risque d'être détruit par l'ajout des dossiers
            node_item = self.model.find_item(sig_item, ctx.get_node())
            index = self.model.index_from_item(node_item)

        # ✅ DERIVED
        elif ctx.role == itemType.DERIVED:
            #! on récupère un analyseNode car derivedTreeItem n'existe pas pour l'instant!
            analysis_item = sig_item.child(ctx.derived_index)
            index = self.model.index_from_item(ctx.derived_index)

        """print(  f'Ligne 217: {index.internalPointer().data.display_name}'+
                f'{ctx.signal.display_name}')"""
        if index is None or not index.isValid():
            return

        # --- Expansion parents ---
        parent = index
        while parent.isValid():
            self.tree.expand(parent)
            parent = parent.parent()

        # --- Sélection explicite ---
        sel_model.blockSignals(True)
        sel_model.select(
                            index,
                            QtCore.QItemSelectionModel.SelectionFlag.ClearAndSelect
                            | QtCore.QItemSelectionModel.SelectionFlag.Rows
                        )
        sel_model.setCurrentIndex(
                                    index,
                                    QtCore.QItemSelectionModel.SelectionFlag.NoUpdate
                                )

        self.tree.scrollTo(
                                    index,
                                    QtWidgets.QAbstractItemView.ScrollHint.PositionAtCenter
                                )
        sel_model.blockSignals(False)

    def checkStates(self,selected=None):
        if selected is not None:

            #? faut-il vraiment interdire l'accès aux actions si un filtre est sélectionné
            if isinstance(selected,SignalObject|DerivedSignalObject):
                has_select=True
                has_ref = self.reference_sig is not None and not selected.is_reference
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
        obj = item.obj

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



    def expand_and_select(self, index: QtCore.QModelIndex):
        if not index or not index.isValid():
            return

        # développer tous les parents
        parent = index
        while parent.isValid():
            self.tree.expand(parent)
            parent = parent.parent()

        # sélectionner l’item
        sel = self.tree.selectionModel()
        with QtCore.QSignalBlocker(sel):
            sel.setCurrentIndex(
                index,
                QtCore.QItemSelectionModel.SelectionFlag.ClearAndSelect
            )

        self.tree.scrollTo(index, QtWidgets.QAbstractItemView.ScrollHint.EnsureVisible)

    def set_reference_signal(self, sig : SignalObject):

        self.reference_sig=sig

