
# controller/channel_tree_controller.py
from PyQt6 import QtCore, QtWidgets

from model.channel_tree_model import ChannelTreeModel
from model.channels import MATCH_BY_NAME, MATCH_BY_CHANNEL, solo_key
from ressources.custom_types import itemType
from ressources.custom_items import SelectionContext


class ChannelTreeController(QtCore.QObject):
    """
    Arbre de la vue « Par voie » : sélection d'une instance (voie d'un fichier) et
    synchronisation avec la sélection faite ailleurs (arbre « Par fichier », graphique).
    """

    item_selected = QtCore.pyqtSignal(SelectionContext)
    # menu contextuel : (SignalObject, clé de la voie logique ou None = automatique)
    link_requested = QtCore.pyqtSignal(object, object)
    # menu contextuel : mode d'appariement "name" / "channel"
    matching_requested = QtCore.pyqtSignal(str)

    def __init__(self, tree: QtWidgets.QTreeView):
        super().__init__()
        self.tree = tree
        self.model: ChannelTreeModel | None = None
        # appariement à la main : glisser une voie sur une autre voie logique
        tree.setDragEnabled(True)
        tree.setAcceptDrops(True)
        tree.setDropIndicatorShown(True)
        tree.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.DragDrop)
        tree.setDefaultDropAction(QtCore.Qt.DropAction.LinkAction)
        tree.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        tree.customContextMenuRequested.connect(self._on_context_menu)

    def set_model(self, model: ChannelTreeModel):
        self.model = model
        self.tree.setModel(model)
        header = self.tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Interactive)
        self.tree.setColumnWidth(0, 250)
        self.tree.setColumnWidth(1, 100)
        self.tree.selectionModel().selectionChanged.connect(self._on_selection_changed)
        # dépliage conservé quand les voies logiques sont reconstruites
        model.modelAboutToBeReset.connect(self._remember_expanded)
        model.modelReset.connect(self._restore_expanded)
        self._expanded = set()

    def _remember_expanded(self):
        self._expanded = {  group.key for row, group in enumerate(self.model.groups())
                            if self.tree.isExpanded(self.model.index(row, 0))}

    def _restore_expanded(self):
        for row, group in enumerate(self.model.groups()):
            if group.key in self._expanded:
                self.tree.expand(self.model.index(row, 0))

    def _on_selection_changed(self, selected, deselected):
        indexes = selected.indexes()
        if not indexes:
            return
        ctx = indexes[0].internalPointer().to_selection_context()
        if ctx is not None:
            self.item_selected.emit(ctx)

    # ---------------- menu contextuel ----------------

    def context_menu(self, index) -> QtWidgets.QMenu:
        """Menu de la vue « Par voie » pour la ligne index (invalide : zone vide)."""
        menu = QtWidgets.QMenu(self.tree)
        obj = index.internalPointer().obj if index.isValid() else None
        if obj is not None and obj.item_type != itemType.CHANNEL:
            group = index.parent().internalPointer().obj
            link_menu = menu.addMenu("Associer à la voie")
            for other in self.model.groups():
                if other is not group:
                    action = link_menu.addAction(other.name)
                    action.triggered.connect(
                        lambda _=False, key=other.key: self.link_requested.emit(obj, key))
            link_menu.setEnabled(not link_menu.isEmpty())
            solo = menu.addAction("Mettre à part")
            solo.setEnabled(len(group.signals) > 1)
            solo.triggered.connect(lambda: self.link_requested.emit(obj, solo_key(obj)))
            auto = menu.addAction("Rétablir l'association automatique")
            auto.setEnabled(obj in group.manual)
            auto.triggered.connect(lambda: self.link_requested.emit(obj, None))
            menu.addSeparator()
        current = self.model.workspace.matching_mode
        for mode, text in ((MATCH_BY_NAME, "Apparier les voies par nom"),
                           (MATCH_BY_CHANNEL, "Apparier les voies par numéro (CH)")):
            action = menu.addAction(text)
            action.setCheckable(True)
            action.setChecked(mode == current)
            action.triggered.connect(lambda _=False, m=mode: self.matching_requested.emit(m))
        return menu

    def _on_context_menu(self, pos):
        menu = self.context_menu(self.tree.indexAt(pos))
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def select_signal(self, sig):
        """Sélectionne (sans émettre item_selected) l'instance de sig, ou rien."""
        sel_model = self.tree.selectionModel()
        index = self.model.signal_index(sig) if sig is not None else QtCore.QModelIndex()
        with QtCore.QSignalBlocker(sel_model):
            if not index.isValid():
                sel_model.clearSelection()
            else:
                self.tree.expand(index.parent())
                sel_model.select(index, QtCore.QItemSelectionModel.SelectionFlag.ClearAndSelect
                                        | QtCore.QItemSelectionModel.SelectionFlag.Rows)
                sel_model.setCurrentIndex(index,
                                          QtCore.QItemSelectionModel.SelectionFlag.NoUpdate)
                self.tree.scrollTo(index)
        self.tree.viewport().update()
