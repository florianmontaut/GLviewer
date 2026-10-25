# controller/channel_tree_controller.py
from PyQt6 import QtCore, QtWidgets

from model.channel_tree_model import ChannelTreeModel, CONTAINERS
from model.channels import MATCH_BY_NAME, MATCH_BY_CHANNEL, solo_key
from ressources.custom_types import itemType, qSignalType
from ressources.custom_items import SelectionContext
from ressources.custom_menu import BaseContextMenu

# actions applicables d'un coup à toutes les voies d'une sélection (voie logique, groupe)
GROUP_ACTIONS = (qSignalType.FILTER, qSignalType.DIFF, qSignalType.OFFSET,
                 qSignalType.OFFSET_X, qSignalType.MODEL)


class ChannelTreeController(QtCore.QObject):
    """
    Arbre de la vue « Par voie » : sélection d'une instance (voie d'un fichier) et
    synchronisation avec la sélection faite ailleurs (arbre « Par fichier », graphique),
    menu contextuel (appariement, groupes, actions sur toutes les voies d'une sélection).
    """

    item_selected = QtCore.pyqtSignal(SelectionContext)
    # menu contextuel : (SignalObject, clé de la voie logique ou None = automatique)
    link_requested = QtCore.pyqtSignal(object, object)
    # menu contextuel : mode d'appariement "name" / "channel"
    matching_requested = QtCore.pyqtSignal(str)
    # menu contextuel, groupes : (opération, argument)
    #   "new" : clés des voies | "add" : (id du groupe, clés) | "remove" : clés
    #   "rename" / "delete" : id du groupe
    group_edit_requested = QtCore.pyqtSignal(str, object)
    # menu contextuel : (voies affichées de la sélection, qSignalType)
    apply_requested = QtCore.pyqtSignal(object, object)
    # groupe sélectionné : ses paramètres (nom) dans le ParameterTree
    group_selected = QtCore.pyqtSignal(object)

    def __init__(self, tree: QtWidgets.QTreeView):
        super().__init__()
        self.tree = tree
        self.model: ChannelTreeModel | None = None
        # plusieurs voies logiques sélectionnées : groupe, action sur toutes leurs voies
        tree.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        # appariement à la main : glisser une voie sur une autre voie logique, une voie
        # logique sur un groupe
        tree.setDragEnabled(True)
        tree.setAcceptDrops(True)
        tree.setDropIndicatorShown(True)
        tree.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.DragDrop)
        tree.setDefaultDropAction(QtCore.Qt.DropAction.LinkAction)
        tree.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        tree.customContextMenuRequested.connect(self._on_context_menu)
        # référence de température définie (« Get temperature rise »)
        self.has_reference = lambda: False

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

    @staticmethod
    def _expand_key(obj):
        return f"group:{obj.id}" if obj.item_type == itemType.CHANNEL_GROUP else obj.key

    def _containers(self):
        for item in self.model._items():
            if item.obj.item_type in CONTAINERS:
                yield item, self.model.index_from_item(item)

    def _remember_expanded(self):
        self._expanded = {self._expand_key(item.obj) for item, index in self._containers()
                          if self.tree.isExpanded(index)}

    def _restore_expanded(self):
        for item, index in self._containers():
            if self._expand_key(item.obj) in self._expanded:
                self.tree.expand(index)

    def _on_selection_changed(self, selected, deselected):
        indexes = selected.indexes()
        if not indexes:
            return
        obj = indexes[0].internalPointer().obj
        if obj.item_type == itemType.CHANNEL_GROUP:
            self.group_selected.emit(obj)
            return
        ctx = indexes[0].internalPointer().to_selection_context()
        if ctx is not None:
            self.item_selected.emit(ctx)

    # ---------------- menu contextuel ----------------

    def _targets(self, index) -> list:
        """Lignes visées : la sélection si elle contient la ligne cliquée, sinon celle-ci."""
        rows = [i.internalPointer().obj for i in self.tree.selectionModel().selectedRows(0)]
        if index.isValid() and index.internalPointer().obj not in rows:
            rows = [index.internalPointer().obj]
        return rows if index.isValid() else []

    def context_menu(self, index) -> QtWidgets.QMenu:
        """Menu de la vue « Par voie » pour la ligne index (invalide : zone vide)."""
        menu = QtWidgets.QMenu(self.tree)
        targets = self._targets(index)
        obj = index.internalPointer().obj if index.isValid() else None
        if obj is not None and obj.item_type not in CONTAINERS and len(targets) == 1:
            self._add_link_actions(menu, index, obj)
        if any(t.item_type in CONTAINERS for t in targets) or len(targets) > 1:
            self._add_apply_menu(menu, targets)
        channels = [t for t in targets if t.item_type == itemType.CHANNEL]
        if channels:
            self._add_channel_group_actions(menu, channels)
        if obj is not None and obj.item_type == itemType.CHANNEL_GROUP and len(targets) == 1:
            rename = menu.addAction("Renommer le groupe…")
            rename.triggered.connect(lambda: self.group_edit_requested.emit("rename", obj.id))
            delete = menu.addAction("Supprimer le groupe")
            delete.triggered.connect(lambda: self.group_edit_requested.emit("delete", obj.id))
        if not menu.isEmpty():
            menu.addSeparator()
        current = self.model.workspace.matching_mode
        for mode, text in ((MATCH_BY_NAME, "Apparier les voies par nom"),
                           (MATCH_BY_CHANNEL, "Apparier les voies par numéro (CH)")):
            action = menu.addAction(text)
            action.setCheckable(True)
            action.setChecked(mode == current)
            action.triggered.connect(lambda _=False, m=mode: self.matching_requested.emit(m))
        return menu

    def _add_link_actions(self, menu, index, sig):
        group = index.parent().internalPointer().obj
        link_menu = menu.addMenu("Associer à la voie")
        for other in self.model.groups():
            if other is not group:
                action = link_menu.addAction(other.name)
                action.triggered.connect(
                    lambda _=False, key=other.key: self.link_requested.emit(sig, key))
        link_menu.setEnabled(not link_menu.isEmpty())
        solo = menu.addAction("Mettre à part")
        solo.setEnabled(len(group.signals) > 1)
        solo.triggered.connect(lambda: self.link_requested.emit(sig, solo_key(sig)))
        auto = menu.addAction("Rétablir l'association automatique")
        auto.setEnabled(sig in group.manual)
        auto.triggered.connect(lambda: self.link_requested.emit(sig, None))
        menu.addSeparator()

    def _add_apply_menu(self, menu, targets):
        """Filtre / analyse sur toutes les voies affichées (cochées) de la sélection."""
        signals = []
        for target in targets:
            for sig in (target.signals if target.item_type in CONTAINERS else [target]):
                if sig.visible and sig not in signals:
                    signals.append(sig)
        apply_menu = menu.addMenu(f"Appliquer aux voies affichées ({len(signals)})")
        apply_menu.setEnabled(bool(signals))
        for action_type in GROUP_ACTIONS:
            action = apply_menu.addAction(BaseContextMenu.ACTION_SPECS[action_type].label)
            if action_type == qSignalType.DIFF:
                action.setEnabled(self.has_reference())
            action.triggered.connect(
                lambda _=False, t=action_type: self.apply_requested.emit(signals, t))
        menu.addSeparator()

    def _add_channel_group_actions(self, menu, channels):
        keys = [channel.key for channel in channels]
        new = menu.addAction("Nouveau groupe avec ces voies…")
        new.triggered.connect(lambda: self.group_edit_requested.emit("new", keys))
        add_menu = menu.addMenu("Ajouter au groupe")
        for group in self.model.user_groups():
            action = add_menu.addAction(group.name)
            action.triggered.connect(
                lambda _=False, gid=group.id: self.group_edit_requested.emit("add", (gid, keys)))
        add_menu.setEnabled(not add_menu.isEmpty())
        in_group = {key for group in self.model.workspace.channel_groups for key in group.keys}
        remove = menu.addAction("Retirer du groupe")
        remove.setEnabled(any(key in in_group for key in keys))
        remove.triggered.connect(lambda: self.group_edit_requested.emit("remove", keys))
        menu.addSeparator()

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
                parent = index.parent()
                while parent.isValid():              # groupe puis voie logique
                    self.tree.expand(parent)
                    parent = parent.parent()
                sel_model.select(index, QtCore.QItemSelectionModel.SelectionFlag.ClearAndSelect
                                        | QtCore.QItemSelectionModel.SelectionFlag.Rows)
                sel_model.setCurrentIndex(index,
                                          QtCore.QItemSelectionModel.SelectionFlag.NoUpdate)
                self.tree.scrollTo(index)
        self.tree.viewport().update()
