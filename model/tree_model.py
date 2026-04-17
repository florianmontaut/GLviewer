
# model/tree_model.py
import numpy as np
import pathlib

from PyQt6.QtCore import Qt, QModelIndex, QAbstractItemModel
from PyQt6.QtGui import QColor,QBrush,QFont,QIcon
from model.tree_item import TreeItem
from model.base_objects import FileObject, SignalObject,Workspace
from model.filters.base_filter import FilterNode
from model.analysis.base_analysis import AnalysisNode
from PyQt6.QtCore import QObject, pyqtSignal

from model.base_objects import SignalObject

PATH=pathlib.Path(__file__).parent.parent


class PipelineTreeModel(QAbstractItemModel):

    new_filter=pyqtSignal(object,object)
    changed_filter=pyqtSignal(object,object)

    def __init__(self, workspace: Workspace, parent=None):
        super().__init__(parent)

        self.workspace = workspace

        self.icon_file              = QIcon(str(PATH)+"/ressources/icons/file.svg")
        self.icon_signal_raw        = QIcon(str(PATH)+"/ressources/icons/signal_raw.svg")
        self.icon_signal_modified   = QIcon(str(PATH)+"/ressources/icons/signal_modified.svg")
        self.icon_filter            = QIcon(str(PATH)+"/ressources/icons/filter.svg")
        self.icon_signal_reference  = QIcon(str(PATH)+"/ressources/icons/signal_reference.svg")

        self.root = TreeItem("Workspace")

        #curseur Global
        self.cursor_x = None  # position du curseur (abscisse)

        # ✅ index par fichier
        self.cursor_Y_values_by_file = {}  # FileObject → list[float]
        self.signal_index_map = {}
        # build signals
        self._build_tree()


    def _build_tree(self):
        self.root.children.clear()

        for file_obj in self.workspace.files:
            self.add_file_subtree(file_obj)

    # ----------------- Build file subtree -----------------

    def add_file_subtree(self, file_obj: FileObject):
        """
        Ajoute un FileObject au modèle et notifie Qt correctement.
        """
        root_index = QModelIndex()
        row = self.root.child_count()  # position d'insertion

        self.beginInsertRows(root_index, row, row)
        file_item = TreeItem(file_obj, self.root)
        self.root.add_child(file_item)

        # Ajouter les signaux
        for sig in file_obj.signals:
            self.add_signal_subtree(sig,file_item)

        self.endInsertRows()
        #la ligne suivante évite les messages d'erreur après le chargement d'un nouveau
        #fichier alors que les curseurs sont présents. En effet sans ces lignes,
        #self.cursor_Y_values_by_file n'a pas été mis à jour
        if self.cursor_x is not None:
            self.updateCursorVal(self.cursor_x)

    # ----------------- Build signal subtree -----------------

    def add_signal_subtree(self, sig: SignalObject, parent:TreeItem):
        sig_item = TreeItem(sig, parent)
        parent.add_child(sig_item)

        # ✅ on mémorise l'index
        index = self.createIndex(len(parent.children)-1,0,sig_item)
        self.signal_index_map[sig] = index


        for node in sig.pipeline:
            filter_item = TreeItem(node, sig_item)
            sig_item.add_child(filter_item)

        # --- Analyses ---
        for analysis in sig.analyses:
            analysis_item = TreeItem(analysis, sig_item)
            sig_item.add_child(analysis_item)

            # Ajouter les signaux DÉRIVÉS de cette analyse
            for derived_sig in sig.derived_signals:
                if (hasattr(derived_sig, 'metadata') and
                    derived_sig.metadata.get('analysis_id') == analysis.id):
                    derived_item = TreeItem(derived_sig, analysis_item)
                    analysis_item.add_child(derived_item)

    def remove_file_subtree(self, file_obj):
        """
        Supprime un FileObject du modèle Qt proprement.
        """
        # trouver l'index du FileObject
        root_item = self.root
        row = None

        for i, child in enumerate(root_item.children):
            if child.data is file_obj:
                row = i
                break

        if row is None:
            return  # sécurité

        parent_index = QModelIndex()
        self.beginRemoveRows(parent_index, row, row)
        root_item.children.pop(row)
        self.endRemoveRows()

    # ---------------------- Model API ----------------------
    def index(self, row, column, parent):
        if not self.hasIndex(row, column, parent):
            return QModelIndex()

        parent_item = self.root if not parent.isValid() else parent.internalPointer()
        child = parent_item.child(row)

        if child:
            return self.createIndex(row, column, child)
        return QModelIndex()

    def parent(self, index):
        if not index.isValid():
            return QModelIndex()

        item = index.internalPointer()
        parent_item = item.parent

        if parent_item == self.root or parent_item is None:
            return QModelIndex()
        return self.createIndex(parent_item.row(), 0, parent_item)

    # méthode inutile car le header est caché
    def headerData(self, section, orientation, role):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            if section == 0:
                return "Signal"
            elif section == 1:
                return "Value @ Cursor"
        return None


    def rowCount(self, parent):
        if not parent.isValid():
            return self.root.child_count()
        return parent.internalPointer().child_count()

    def columnCount(self, parent):

    # 0 = Nom + icône + Visible (checkbox)
    # 1 = Valeur au curseur
        return 2


    # ---------------------- Display ----------------------
    def data(self, index, role):
        if not index.isValid():
            return None

        #origine=self.sender()
        #print(origine)
        item = index.internalPointer()
        obj = item.data
        col = index.column()

        # ---------------- colonne 0 : nom ----------------
        if role == Qt.ItemDataRole.DisplayRole and col == 0:
            if isinstance(obj, (FilterNode, AnalysisNode)):
                return obj.display_name
            else:
                return obj.name

        # ---------------- colonne 1 : valeur au curseur ----------------
        if role == Qt.ItemDataRole.DisplayRole and col == 1:
            if isinstance(obj, SignalObject):
                if self.cursor_x is None:
                    return "-"

                file=obj.file
                val=self.cursor_Y_values_by_file[file][obj.name]

                if isinstance(val, (float, np.floating)):
                    return f"{val:.2f}{obj.unit}"
                else:
                    return "-"


        if role == Qt.ItemDataRole.FontRole:
            if isinstance(obj, SignalObject) and obj.is_selected:
                font = QFont()
                font.setBold(True)
                return font

        if role == Qt.ItemDataRole.ForegroundRole:
            if isinstance(obj, SignalObject) and obj.is_reference:
                return QBrush(QColor("#D32F2F"))  # rouge profond
            else:
                return QBrush(QColor("#000000"))  # noir profond

    # ---------------- Checkbox ----------------
        if role == Qt.ItemDataRole.CheckStateRole and isinstance(obj, SignalObject) and col == 0:
            return Qt.CheckState.Checked if obj.visible else Qt.CheckState.Unchecked

    # ---------------- Background color ----------------
        if role == Qt.ItemDataRole.BackgroundRole:
            if isinstance(obj, SignalObject):
                # Couleur de fond = couleur du signal
                color = QColor(obj.pen.color())
                # léger alpha pour rester lisible
                color.setAlpha(150)
                return QBrush(color)

        # Icône uniquement sur la colonne 0
        if role == Qt.ItemDataRole.DecorationRole and col == 0:

            # FileObject
            if isinstance(obj, FileObject):
                return self.icon_file

            # SignalObject
            if isinstance(obj, SignalObject):

                if obj.is_reference:
                    return self.icon_signal_reference
                elif obj.is_modified:
                    return self.icon_signal_modified
                else:
                    return self.icon_signal_raw

            # FilterNode
            if isinstance(obj, FilterNode):
                return self.icon_filter

        return None

    def updateCursorVal(self,x):

        #MAJ de la colonne value / on peut envisager une version où la colonne serait  déplaçable
        self.cursor_x=x

        for file in self.workspace.files:
            xs = file.signals[0].x
            idx = np.argmin(np.abs(xs - np.ones(len(xs))*x))
            self.cursor_Y_values_by_file[file]=file.get_Y_from_X_index(idx)

        tl = self.index(0, 1, QModelIndex())
        br = self.index(self.rowCount(QModelIndex()) - 1, 1, QModelIndex())
        self.dataChanged.emit(tl, br, [Qt.ItemDataRole.DisplayRole])


    # ---------------------- Checkbox handling ----------------------

    def setData(self, index, value, role):
        if not index.isValid():
            return False

        item = index.internalPointer()
        obj = item.data

        if isinstance(obj, SignalObject) and role == Qt.ItemDataRole.CheckStateRole:
            #value est un int ! pas un Qt.CheckState, il faut donc utiliser la méthode .value
            #afin de récupèrer l'int équivalent de enum Qt.CheckState
            obj.visible = (value == Qt.CheckState.Checked.value)
            #le troisième argument de emit permet d'indiquer ce qui à été modifié
            self.dataChanged.emit(  index,
                                    index,
                                    [Qt.ItemDataRole.CheckStateRole]
                                )
            return True
        return False

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags

        obj = index.internalPointer().data
        flags = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled

        if isinstance(obj, SignalObject):
            flags |= Qt.ItemFlag.ItemIsUserCheckable

        return flags

    # ---------------------- Update pipeline (undo/redo) ----------------------

    def insert_filter(self, sig: SignalObject,
                            filter_node: FilterNode,
                            index: int)-> QModelIndex | None:
        sig_item = self._find_item(self.root, sig)
        if not sig_item:
            return

        parent_index = self.index(  sig_item.row(),
                                    0,
                                    self.index(sig_item.parent.row(), 0, QModelIndex()))

        self.beginInsertRows(parent_index, index, index)
        filter_item = TreeItem(filter_node, sig_item)
        sig_item.children.insert(index, filter_item)
        self.endInsertRows()

        self.new_filter.emit(sig_item,index)

    def remove_filter(self, sig: SignalObject, index: int):
        sig_item = self._find_item(self.root, sig)
        if not sig_item:
            return

        parent = self.index(sig_item.row(), 0, self.parent(self.index(sig_item.row(), 0, QModelIndex())))
        self.beginRemoveRows(parent, index, index)
        sig_item.children.pop(index)
        self.endRemoveRows()
        self.changed_filter.emit(sig_item,None)

    def update_filter(self, sig: SignalObject, index: int):
        """
        Mise à jour visuelle d'un FilterNode existant.
        Robuste aux remplacements IMMUTABLES.
        """
        sig_item = self._find_item(self.root, sig)
        if sig_item is None:
            return

        if index < 0 or index >= sig_item.child_count():
            return

        filter_item = sig_item.child(index)

        #  synchronisation explicite avec la source de vérité
        filter_item.data = sig.pipeline[index]

        parent_index = self.index(
            sig_item.row(),
            0,
            self.index(sig_item.parent.row(), 0, QModelIndex())
        )

        model_index = self.index(index, 0, parent_index)

        self.dataChanged.emit(
            model_index,
            model_index,
            [
                Qt.ItemDataRole.DisplayRole,
                Qt.ItemDataRole.DecorationRole
            ]
        )
        self.changed_filter.emit(sig_item,index)

    def insert_analysis(self, sig: SignalObject, analysis_node, index: int):
        """Insère une analyse dans l'arbre."""
        sig_item = self._find_item(self.root, sig)
        if not sig_item:
            return
        #! attention à la colonne 0 commune aux filtres,analyses et derivedSignal
        #! il est probable que cela trompe la gestion des index!
        parent_index = self.index(  sig_item.row(),
                                    0,
                                    self.index(sig_item.parent.row(),0,QModelIndex())
                                    )

        self.beginInsertRows(parent_index, index, index)
        analysis_item = TreeItem(analysis_node, sig_item)
        sig_item.children.insert(index, analysis_item)
        self.endInsertRows()


    def remove_analysis(self, sig: SignalObject, index: int):
        """Supprime une analyse de l'arbre."""
        sig_item = self._find_item(self.root, sig)
        if not sig_item:
            return

        parent = self.index(sig_item.row(),
                            0,
                            self.parent(self.index(sig_item.row(), 0, QModelIndex())))
        self.beginRemoveRows(parent, index, index)
        sig_item.children.pop(index)
        self.endRemoveRows()


    def update_analysis(self, sig: SignalObject, index: int):
        """Met à jour l'affichage d'une analyse après modification."""
        sig_item = self._find_item(self.root, sig)
        if sig_item is None:
            return

        if index < 0 or index >= sig_item.child_count():
            return

        analysis_item = sig_item.child(index)
        analysis_item.data = sig.analyses[index]

        parent_index = self.index(
                                    sig_item.row(),
                                    0,
                                    self.index( sig_item.parent.row(),
                                                0,
                                                QModelIndex())
                                )

        model_index = self.index(index, 0, parent_index)

        self.dataChanged.emit(
                            model_index,
                            model_index,
                            [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.DecorationRole]
                            )
    # ---------------------- Search ----------------------

    def _find_item(self, item: TreeItem, target_obj):
        if item.data is target_obj:
            return item
        for child in item.children:
            found = self._find_item(child, target_obj)
            if found:
                return found
        return None



    '''
    def update_filter(self, sig: SignalObject, index: int):
        """
        Notifie Qt qu'un filtre existant a changé (nom, paramètres, icône),
        sans modifier la structure de l'arbre.
        """
        sig_item = self._find_item(self.root, sig)
        if not sig_item:
            return

        # récupérer l'item FilterNode correspondant
        try:
            filter_item = sig_item.child(index)
        except Exception:
            return

        # QModelIndex de l'item filtre (colonne 0 = nom / icône)
        filter_index = self.createIndex(index, 0, filter_item)

        # notifier Qt uniquement sur ce qui peut changer
        self.dataChanged.emit(  filter_index, filter_index,
                                    [
                                        Qt.ItemDataRole.DisplayRole,
                                        Qt.ItemDataRole.DecorationRole
                                    ]
                            )
    '''
