
# controller/channel_tree_controller.py
from PyQt6 import QtCore, QtWidgets

from model.channel_tree_model import ChannelTreeModel
from ressources.custom_items import SelectionContext


class ChannelTreeController(QtCore.QObject):
    """
    Arbre de la vue « Par voie » : sélection d'une instance (voie d'un fichier) et
    synchronisation avec la sélection faite ailleurs (arbre « Par fichier », graphique).
    """

    item_selected = QtCore.pyqtSignal(SelectionContext)

    def __init__(self, tree: QtWidgets.QTreeView):
        super().__init__()
        self.tree = tree
        self.model: ChannelTreeModel | None = None

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
