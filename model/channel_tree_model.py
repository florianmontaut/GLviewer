
# model/channel_tree_model.py
"""
Arbre de la vue « Par voie » : les voies logiques (même voie dans plusieurs fichiers) et,
sous chacune, ses instances (une voie par fichier, libellée par l'étiquette du fichier).
Même Workspace que l'arbre « Par fichier » : seule la présentation change.
"""
from PyQt6.QtCore import Qt, QModelIndex, QAbstractItemModel, QMimeData, pyqtSignal
from PyQt6.QtGui import QColor, QBrush, QFont

from model.tree_item import TreeItem
from model.channels import group_channels
from ressources.custom_types import itemType


class ChannelTreeModel(QAbstractItemModel):

    # cases à cocher : voies dont la visibilité vient de changer
    visibility_changed = pyqtSignal(object)
    # glisser-déposer d'une voie sur une voie logique : (SignalObject, clé de la voie)
    link_requested = pyqtSignal(object, object)

    MIME_TYPE = "application/x-glviewer-signal"

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
        for group in group_channels(self.workspace):
            group_item = TreeItem(group, parent=self.root)
            self.root.add_child(group_item)
            for sig in group.signals:
                group_item.add_child(TreeItem(sig, parent=group_item))
        self.endResetModel()

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
            return Qt.ItemFlag.NoItemFlags
        flags = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
        if index.column() == 0:
            flags |= Qt.ItemFlag.ItemIsUserCheckable
        # une voie d'un fichier se glisse sur une voie logique (ou l'une de ses voies)
        flags |= Qt.ItemFlag.ItemIsDropEnabled
        if index.internalPointer().obj.item_type != itemType.CHANNEL:
            flags |= Qt.ItemFlag.ItemIsDragEnabled
        return flags

    # ---------------- glisser-déposer ----------------

    def supportedDragActions(self):
        return Qt.DropAction.LinkAction

    def supportedDropActions(self):
        return Qt.DropAction.LinkAction

    def mimeTypes(self):
        return [self.MIME_TYPE]

    def mimeData(self, indexes):
        ids = {index.internalPointer().obj.id for index in indexes
               if index.internalPointer().obj.item_type != itemType.CHANNEL}
        data = QMimeData()
        data.setData(self.MIME_TYPE, ",".join(sorted(ids)).encode())
        return data

    def _drop_target(self, parent):
        """Voie logique visée par un dépôt (sur elle ou sur l'une de ses voies)."""
        if not parent.isValid():
            return None
        item = parent.internalPointer()
        if item.obj.item_type != itemType.CHANNEL:
            item = item.parent_item
        return item.obj

    def canDropMimeData(self, data, action, row, column, parent):
        return data.hasFormat(self.MIME_TYPE) and self._drop_target(parent) is not None

    def dropMimeData(self, data, action, row, column, parent):
        group = self._drop_target(parent)
        if group is None or not data.hasFormat(self.MIME_TYPE):
            return False
        ids = bytes(data.data(self.MIME_TYPE)).decode().split(",")
        for sig in self._signals():
            if sig.id in ids and sig not in group.signals:
                self.link_requested.emit(sig, group.key)
        return True

    def _signals(self):
        return [item.obj for group_item in self.root.children for item in group_item.children]

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        obj = index.internalPointer().obj
        col = index.column()
        if obj.item_type == itemType.CHANNEL:
            return self._channel_data(obj, col, role)
        return self._instance_data(obj, col, role)

    def _channel_data(self, group, col, role):
        if role == Qt.ItemDataRole.DisplayRole and col == 0:
            return f"{group.name} ({len(group.signals)})"
        if role == Qt.ItemDataRole.CheckStateRole and col == 0:
            visible = group.visible
            if visible is None:
                return Qt.CheckState.PartiallyChecked
            return Qt.CheckState.Checked if visible else Qt.CheckState.Unchecked
        if role == Qt.ItemDataRole.ToolTipRole:
            files = ", ".join(sig.file.label or sig.file.name for sig in group.signals)
            return f"{group.name} : présente dans {len(group.signals)} fichier(s)\n{files}"
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
        for group_item in self.root.children:
            if sig in group_item.obj.signals:
                return group_item.obj
        return None

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if not index.isValid() or role != Qt.ItemDataRole.CheckStateRole:
            return False
        item = index.internalPointer()
        visible = value in (Qt.CheckState.Checked.value, Qt.CheckState.Checked)
        if item.obj.item_type == itemType.CHANNEL:
            signals = list(item.obj.signals)
        else:
            signals = [item.obj]
        for sig in signals:
            sig.visible = visible
        self.refresh()
        self.visibility_changed.emit(signals)
        return True

    # ---------------- recherche / mise à jour ----------------

    def index_from_item(self, item) -> QModelIndex:
        if item is None or item.parent_item is None:
            return QModelIndex()
        return self.createIndex(item.row(), 0, item)

    def signal_index(self, sig) -> QModelIndex:
        """Index de l'instance d'une voie (QModelIndex() invalide si absente)."""
        for group_item in self.root.children:
            for item in group_item.children:
                if item.obj is sig:
                    return self.index_from_item(item)
        return QModelIndex()

    def groups(self):
        return [item.obj for item in self.root.children]

    def refresh(self):
        """Visibilité, sélection, valeurs au curseur : toutes les lignes (sans reconstruire)."""
        last_col = self.columnCount() - 1
        if self.root.child_count():
            self.dataChanged.emit(self.index(0, 0),
                                  self.index(self.root.child_count() - 1, last_col))
        for row, group_item in enumerate(self.root.children):
            if group_item.child_count():
                parent = self.index(row, 0)
                self.dataChanged.emit(self.index(0, 0, parent),
                                      self.index(group_item.child_count() - 1, last_col, parent))
