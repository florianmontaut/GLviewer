
# model/channel_tree_model.py
"""
Arbre de la vue « Par voie » : les voies logiques (même voie dans plusieurs fichiers) et,
sous chacune, ses instances (une voie par fichier, libellée par l'étiquette du fichier).
Les groupes créés par l'utilisateur (ex: « Bobinages ») rassemblent des voies logiques
au premier niveau.
Même Workspace que l'arbre « Par fichier » : seule la présentation change.
"""
from PyQt6.QtCore import Qt, QModelIndex, QAbstractItemModel, QMimeData, pyqtSignal
from PyQt6.QtGui import QColor, QBrush, QFont

from model.tree_item import TreeItem
from model.channels import build_channel_tree
from ressources.custom_types import itemType

# lignes « voie logique » et « groupe » (les autres lignes sont des voies de fichiers)
CONTAINERS = (itemType.CHANNEL, itemType.CHANNEL_GROUP)


class ChannelTreeModel(QAbstractItemModel):

    # cases à cocher : voies dont la visibilité vient de changer
    visibility_changed = pyqtSignal(object)
    # glisser-déposer d'une voie sur une voie logique : (SignalObject, clé de la voie)
    link_requested = pyqtSignal(object, object)
    # glisser-déposer de voies logiques : (clés des voies, id du groupe ou None = hors groupe)
    group_requested = pyqtSignal(object, object)

    MIME_TYPE = "application/x-glviewer-signal"
    CHANNEL_MIME_TYPE = "application/x-glviewer-channel"

    def __init__(self, workspace, cursor_value=None, parent=None):
        """
        Args:
            workspace       : Workspace affiché
            cursor_value    : callable(SignalObject) -> valeur au curseur (ou None)
        """
        super().__init__(parent)
        self.workspace = workspace
        self.cursor_value = cursor_value or (lambda sig: None)
        self.root = TreeItem("Channels")
        self.rebuild()

    # ---------------- construction ----------------

    def rebuild(self):
        """Reconstruit les voies logiques (fichier ajouté / retiré, étiquette...)."""
        self.beginResetModel()
        self.root = TreeItem("Channels")
        for entry in build_channel_tree(self.workspace):
            if entry.item_type == itemType.CHANNEL_GROUP:
                group_item = TreeItem(entry, parent=self.root)
                self.root.add_child(group_item)
                for channel in entry.channels:
                    self._add_channel(channel, group_item)
            else:
                self._add_channel(entry, self.root)
        self.endResetModel()

    @staticmethod
    def _add_channel(channel, parent):
        channel_item = TreeItem(channel, parent=parent)
        parent.add_child(channel_item)
        for sig in channel.signals:
            channel_item.add_child(TreeItem(sig, parent=channel_item))

    # ---------------- API Qt ----------------

    def index(self, row, column, parent=QModelIndex()):
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        parent_item = self.root if not parent.isValid() else parent.internalPointer()
        child = parent_item.child(row)
        return self.createIndex(row, column, child) if child else QModelIndex()

    def parent(self, index=QModelIndex()):
        if not index.isValid():
            return QModelIndex()
        parent_item = index.internalPointer().parent_item
        if parent_item is None or parent_item is self.root:
            return QModelIndex()
        return self.createIndex(parent_item.row(), 0, parent_item)

    def rowCount(self, parent=QModelIndex()):
        if parent.column() > 0:
            return 0
        item = self.root if not parent.isValid() else parent.internalPointer()
        return item.child_count()

    def columnCount(self, parent=QModelIndex()):
        # 0 = voie / fichier, 1 = valeur au curseur
        return 2

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return ("Voie", "Valeur au curseur")[section]
        return None

    def flags(self, index):
        if not index.isValid():
            # dépôt d'une voie logique hors de tout groupe
            return Qt.ItemFlag.ItemIsDropEnabled
        flags = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
        if index.column() == 0:
            flags |= Qt.ItemFlag.ItemIsUserCheckable
        # une voie d'un fichier se glisse sur une voie logique (ou l'une de ses voies),
        # une voie logique sur un groupe
        flags |= Qt.ItemFlag.ItemIsDropEnabled
        if index.internalPointer().obj.item_type != itemType.CHANNEL_GROUP:
            flags |= Qt.ItemFlag.ItemIsDragEnabled
        return flags

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        obj = index.internalPointer().obj
        col = index.column()
        if obj.item_type in CONTAINERS:
            return self._container_data(obj, col, role)
        return self._instance_data(obj, col, role)

    def _container_data(self, obj, col, role):
        is_group = obj.item_type == itemType.CHANNEL_GROUP
        if role == Qt.ItemDataRole.DisplayRole and col == 0:
            if is_group:
                return f"{obj.name} ({len(obj.channels)} voie(s))"
            return f"{obj.name} ({len(obj.signals)})"
        if role == Qt.ItemDataRole.CheckStateRole and col == 0:
            visible = obj.visible
            if visible is None:
                return Qt.CheckState.PartiallyChecked
            return Qt.CheckState.Checked if visible else Qt.CheckState.Unchecked
        if role == Qt.ItemDataRole.FontRole and is_group:
            font = QFont()
            font.setBold(True)
            return font
        if role == Qt.ItemDataRole.ToolTipRole:
            if is_group:
                names = ", ".join(channel.name for channel in obj.channels) or "aucune voie"
                return f"Groupe {obj.name} : {names}"
            files = ", ".join(sig.file.label or sig.file.name for sig in obj.signals)
            return f"{obj.name} : présente dans {len(obj.signals)} fichier(s)\n{files}"
        return None

    def _instance_data(self, sig, col, role):
        file_obj = sig.file
        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                text = file_obj.label or file_obj.name
                group = self._group_of(sig)
                if group is not None and sig.name != group.name and \
                   not group.name.endswith(f"· {sig.name}"):
                    text += f" ({sig.name})"
                return text
            value = self.cursor_value(sig)
            return f"{value:.2f}{sig.unit}" if value is not None else "-"
        if role == Qt.ItemDataRole.CheckStateRole and col == 0:
            return Qt.CheckState.Checked if sig.visible else Qt.CheckState.Unchecked
        if role == Qt.ItemDataRole.BackgroundRole and col == 0 and sig.pen is not None:
            color = QColor(sig.pen.color())
            color.setAlpha(150)
            return QBrush(color)
        manual = sig in self._group_of(sig).manual
        if role == Qt.ItemDataRole.FontRole and (sig.is_selected or manual):
            font = QFont()
            font.setBold(sig.is_selected)
            font.setItalic(manual)       # associée à la main
            return font
        if role == Qt.ItemDataRole.ToolTipRole:
            tip = f"{sig.name} — {file_obj.name}\n{file_obj.address}"
            if sig.channel_id:
                tip = f"{sig.channel_id} : {tip}"
            if manual:
                tip += "\nAssociée à la main (clic droit : rétablir l'association automatique)"
            return tip
        return None

    def _group_of(self, sig):
        for channel in self.groups():
            if sig in channel.signals:
                return channel
        return None

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if not index.isValid() or role != Qt.ItemDataRole.CheckStateRole:
            return False
        item = index.internalPointer()
        visible = value in (Qt.CheckState.Checked.value, Qt.CheckState.Checked)
        if item.obj.item_type in CONTAINERS:
            signals = list(item.obj.signals)
        else:
            signals = [item.obj]
        for sig in signals:
            sig.visible = visible
        self.refresh()
        self.visibility_changed.emit(signals)
        return True

    # ---------------- glisser-déposer ----------------

    def supportedDragActions(self):
        return Qt.DropAction.LinkAction

    def supportedDropActions(self):
        return Qt.DropAction.LinkAction

    def mimeTypes(self):
        return [self.MIME_TYPE, self.CHANNEL_MIME_TYPE]

    def mimeData(self, indexes):
        objs = [index.internalPointer().obj for index in indexes]
        data = QMimeData()
        ids = sorted({obj.id for obj in objs if obj.item_type not in CONTAINERS})
        if ids:
            data.setData(self.MIME_TYPE, ",".join(ids).encode())
        keys = [obj.key for obj in dict.fromkeys(objs) if obj.item_type == itemType.CHANNEL]
        if keys:
            data.setData(self.CHANNEL_MIME_TYPE, "\n".join(keys).encode())
        return data

    def _drop_target(self, parent):
        """Voie logique visée par un dépôt (sur elle ou sur l'une de ses voies)."""
        if not parent.isValid():
            return None
        item = parent.internalPointer()
        if item.obj.item_type not in CONTAINERS:
            item = item.parent_item
        return item.obj if item.obj.item_type == itemType.CHANNEL else None

    def _group_target(self, parent):
        """Groupe visé par le dépôt d'une voie logique (None : hors groupe)."""
        item = parent.internalPointer() if parent.isValid() else None
        while item is not None and item is not self.root:
            if item.obj.item_type == itemType.CHANNEL_GROUP:
                return item.obj
            item = item.parent_item
        return None

    def canDropMimeData(self, data, action, row, column, parent):
        if data.hasFormat(self.CHANNEL_MIME_TYPE):
            return True
        return data.hasFormat(self.MIME_TYPE) and self._drop_target(parent) is not None

    def dropMimeData(self, data, action, row, column, parent):
        if data.hasFormat(self.CHANNEL_MIME_TYPE):
            keys = bytes(data.data(self.CHANNEL_MIME_TYPE)).decode().split("\n")
            group = self._group_target(parent)
            self.group_requested.emit(keys, group.id if group is not None else None)
            return True
        group = self._drop_target(parent)
        if group is None or not data.hasFormat(self.MIME_TYPE):
            return False
        ids = bytes(data.data(self.MIME_TYPE)).decode().split(",")
        for sig in self._signals():
            if sig.id in ids and sig not in group.signals:
                self.link_requested.emit(sig, group.key)
        return True

    def _signals(self):
        return [sig for channel in self.groups() for sig in channel.signals]

    # ---------------- recherche / mise à jour ----------------

    def _items(self, parent=None):
        """Toutes les lignes de l'arbre (parcours en profondeur)."""
        parent = parent or self.root
        for item in parent.children:
            yield item
            yield from self._items(item)

    def index_from_item(self, item) -> QModelIndex:
        if item is None or item.parent_item is None:
            return QModelIndex()
        return self.createIndex(item.row(), 0, item)

    def signal_index(self, sig) -> QModelIndex:
        """Index de l'instance d'une voie (QModelIndex() invalide si absente)."""
        for item in self._items():
            if item.obj is sig:
                return self.index_from_item(item)
        return QModelIndex()

    def object_index(self, obj) -> QModelIndex:
        """Index d'une voie logique ou d'un groupe (QModelIndex() invalide si absent)."""
        return self.signal_index(obj)

    def groups(self):
        """Voies logiques (ChannelGroup), groupes de l'utilisateur compris."""
        return [item.obj for item in self._items() if item.obj.item_type == itemType.CHANNEL]

    def user_groups(self):
        return [item.obj for item in self.root.children
                if item.obj.item_type == itemType.CHANNEL_GROUP]

    def refresh(self):
        """Visibilité, sélection, valeurs au curseur : toutes les lignes (sans reconstruire)."""
        last_col = self.columnCount() - 1
        for parent in [self.root, *self._items()]:
            if not parent.child_count():
                continue
            parent_index = self.index_from_item(parent)
            self.dataChanged.emit(self.index(0, 0, parent_index),
                                  self.index(parent.child_count() - 1, last_col, parent_index))
