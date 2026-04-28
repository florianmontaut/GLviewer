
# controller/tree_controller.py

from PyQt6 import QtCore,QtGui,QtWidgets
from model.base_objects import SignalObject,DerivedSignalObject,SelectionContext

from model.tree_item import TreeItem
from model.tree_model import PipelineTreeModel
from PyQt6.QtWidgets import QTreeView

from controller.tree_context_menu_controller import TreeContextMenu

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
    """def _on_selection_changed(self, selected=None, deselected=None):
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
            self.checkStates()"""

    def _on_selection_changed(self, selected, deselected):
        if selected is None:
            return
        if not selected.indexes():
            return

        index = selected.indexes()[0]
        item: TreeItem = index.internalPointer()

        obj=item.data
        obj.is_selected = True

        ctx = self._build_selection_context(item)
        if deselected is not None or not deselected:
            indexes = deselected.indexes()
            for index in indexes:
                item: TreeItem = index.internalPointer()
                obj = item.data
                obj.is_selected = False
        try:
            print(  "Tree_controller ligne 123: _on_selection_changed => méthode appelée en cliquant sur un treeItem: \n"+
                    f'Signal: {ctx.signal.display_name}, role: {ctx.role}, filter index: {ctx.filter_index}'+
                    f', Analysis index: {ctx.analysis_index}, derived index: {ctx.derived_index}\n')
        except:
            print('failed : échec d\'impression de données du CTX (Tree_controller)\n')
        self.item_selected.emit(ctx)


    def _build_selection_context(self, item: TreeItem) -> SelectionContext:
        role = item.role
        obj = item.data


        if role == custom_items.itemType.FILE:
            return SelectionContext(
                role=role,
                signal=obj,
                item=item
            )

        if role == custom_items.itemType.RAW:
            return SelectionContext(
                role=role,
                signal=obj,
                item=item
            )

        if role == custom_items.itemType.FILTER:
            sig = item.parent.data
            return SelectionContext(
                role=role,
                signal=sig,
                filter_index=sig.pipeline.index(obj),
                item=item
            )

        if role == custom_items.itemType.ANALYSE:
            sig = item.parent.data
            return SelectionContext(
                role=role,
                signal=sig,
                analysis_index=sig.analyses.index(obj),
                item=item
            )

        if role == custom_items.itemType.DERIVED:
            analysis_item = item.parent
            sig_item = analysis_item.parent
            sig = sig_item.data
            return SelectionContext(
                role=role,
                signal=sig,
                derived_index=sig.derived_signals.index(obj),
                item=item
            )

        raise RuntimeError(f"Unhandled TreeItem role: {role}")


    def find_treeItem(self,sig):

        return self.model.find_item(self.model.root,sig)

    def select_tree_from_context(self, ctx: SelectionContext):
        sel_model = self.tree.selectionModel()
        sig_item = self.find_treeItem(ctx.signal)
        if sig_item is None:
            return
        index = None
        root_index   = self.model.parent( item = sig_item)
        parent_index = self.model.index(  sig_item.row(),
                                        0,
                                        root_index)
        # ✅ RAW signal
        if ctx.role == custom_items.itemType.RAW:
            index = self.model.signal_index_map.get(ctx.signal)

        # ✅ FILTER
        elif ctx.role == custom_items.itemType.FILTER:
            index = self.model.index(ctx.filter_index, 0, parent_index)

        # ✅ ANALYSE
        elif ctx.role == custom_items.itemType.ANALYSE:
            analysis_item = sig_item.child(ctx.analysis_index)
            index = self.model.index(ctx.analysis_index, 0, parent_index)

        # ✅ DERIVED
        elif ctx.role == custom_items.itemType.DERIVED:
            #! on récupère un analyseNode car derivedTreeItem n'existe pas pour l'instant!
            analysis_item = sig_item.child(ctx.derived_index)
            index = self.model.index(ctx.derived_index, 0, parent_index)

        print(  f'Ligne 217: {index.internalPointer().data.display_name}'+
                f'{ctx.signal.display_name}')
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

