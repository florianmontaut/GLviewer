
# model/tree_model.py
import numpy as np
import pathlib

from PyQt6.QtCore import Qt, QModelIndex, QAbstractItemModel
from PyQt6.QtGui import QColor,QBrush,QFont,QIcon
from model.tree_item import TreeItem
from model.benchmark import power_text
from model.base_objects import FileObject, SignalObject,Workspace
from model.filters.base_filter import FilterNode
from model.analysis.base_analysis import AnalysisNode
from PyQt6.QtCore import QObject, pyqtSignal

from model.base_objects import SignalObject
from ressources.custom_items import itemType,ModelChangeEvent,ActionModifier

PATH=pathlib.Path(__file__).parent.parent


class PipelineTreeModel(QAbstractItemModel):

    node_event          = pyqtSignal(object)

    def __init__(self, workspace: Workspace, parent=None):
        super().__init__(parent)

        self.workspace = workspace

        self.icon_file              = QIcon(str(PATH)+"/ressources/icons/file.svg")
        self.icon_signal_raw        = QIcon(str(PATH)+"/ressources/icons/signal_raw.svg")
        self.icon_signal_modified   = QIcon(str(PATH)+"/ressources/icons/signal_modified.svg")
        self.icon_filter            = QIcon(str(PATH)+"/ressources/icons/filter.svg")
        self.icon_signal_reference  = QIcon(str(PATH)+"/ressources/icons/signal_reference.svg")
        #! Comment le code peut-il fonctionner sans erreur, TreeItem attend data, role et parent:
        self.root = TreeItem("Workspace")

        #curseur Global
        self.cursor_x = None  # position du curseur (abscisse)

        # valeur de chaque signal au curseur (après filtres) : SignalObject -> float
        self.cursor_values = {}
        # pas de cache des QModelIndex des signaux (cf. signal_index) : Qt recommande
        # de ne pas conserver un QModelIndex, l'arbre est la seule source de vérité
        # build signals
        self._build_tree()

    
    def emit_node_event(self, action, item):
        ctx = item.to_selection_context()

        if ctx is None:
            return

        self.node_event.emit(
                                ModelChangeEvent(
                                    action=action,
                                    context=ctx
                                )
                            )



    def _build_tree(self):
        self.root.children.clear()

        for file_obj in self.workspace.files:
            self.add_file_subtree(file_obj)

    # ----------------- Build file subtree -----------------

    def add_file_subtree(self, file_obj: FileObject, row: int | None = None):
        """
        Ajoute un FileObject au modèle (en fin de liste, ou à la position row : fichier
        remis par un undo) et notifie Qt correctement.
        """
        root_index = QModelIndex()
        if row is None or row > self.root.child_count():
            row = self.root.child_count()  # position d'insertion

        self.beginInsertRows(root_index, row, row)
        file_item = TreeItem(file_obj, parent = self.root)
        self.root.insert_child(row, file_item)

        # Ajouter les signaux
        for sig in file_obj.signals:
            self.add_signal_subtree(sig,file_item)

        self.endInsertRows()
        #la ligne suivante évite les messages d'erreur après le chargement d'un nouveau
        #fichier alors que les curseurs sont présents. En effet sans ces lignes,
        #self.cursor_values ne contiendrait pas les voies du nouveau fichier
        if self.cursor_x is not None:
            self.updateCursorVal(self.cursor_x)

    # ----------------- Build signal subtree -----------------

    def add_signal_subtree(self, sig: SignalObject, parent:TreeItem):
        sig_item = TreeItem(sig, parent = parent)
        parent.add_child(sig_item)


        for node in sig.pipeline.values():
            filter_item = TreeItem( node,
                                    parent = sig_item,
                                    )
            sig_item.add_child(filter_item)

        # --- Analyses ---
        for analysis in sig.analyses.values(): #! orderedDict
            # l'analyse et ses signaux DÉRIVÉS
            sig_item.add_child(self._make_node_item(sig, analysis, sig_item))

    def insert_signal(self, sig, row: int | None = None):
        """Ajoute une voie (voie calculée) sous son fichier, à la position row."""
        file_item = self.find_item(self.root, sig.file)
        if file_item is None:
            return
        if row is None or row > file_item.child_count():
            row = file_item.child_count()
        self.beginInsertRows(self.index_from_item(file_item), row, row)
        sig_item = TreeItem(sig, parent=file_item)
        file_item.insert_child(row, sig_item)
        for node in sig.pipeline.values():
            sig_item.add_child(TreeItem(node, parent=sig_item))
        for analysis in sig.analyses.values():
            sig_item.add_child(self._make_node_item(sig, analysis, sig_item))
        self.endInsertRows()
        if self.cursor_x is not None:
            self.updateCursorVal(self.cursor_x)

    def remove_signal(self, sig):
        """Retire une voie (voie calculée) de l'arbre."""
        item = self.find_item(self.root, sig)
        if item is None:
            return
        row = item.row()
        self.beginRemoveRows(self.index_from_item(item.parent_item), row, row)
        item.parent_item.children.pop(row)
        self.endRemoveRows()

    def remove_file_subtree(self, file_obj):
        """
        Supprime un FileObject du modèle Qt proprement.
        """
        # trouver l'index du FileObject
        root_item = self.root

        row = None

        for i, child in enumerate(root_item.children):
            if child.obj is file_obj:
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
        """Retourne l'index Qt pour une position donnée."""
        if not self.hasIndex(row, column, parent):
            return QModelIndex()

        parent_item = self.root if not parent.isValid() else parent.internalPointer()
        child = parent_item.child(row)

        if child:
            return self.createIndex(row, column, child)
        return QModelIndex()

    def parent(self, index = None,item=None):
        """Retourne l'index parent d'un index donné."""

        if item is None:
            if index is None :
                return QModelIndex()
            if not index.isValid():
                return QModelIndex()
            item = index.internalPointer()
        parent_item = item.parent_item

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


    def index_from_item(self, item: TreeItem):
        if item is None or item.parent_item is None:
            return QModelIndex()

        return self.createIndex(item.row(), 0, item)


    # ---------------------- Display ----------------------
    def data(self, index, role):
        if not index.isValid():
            return None

        #origine=self.sender()
        #print(origine)
        item = index.internalPointer()
        obj = item.obj
        obj_type : itemType = obj.item_type
        col = index.column()

        # ---------------- colonne 0 : nom ----------------
        # analyse dont le dernier recalcul a échoué : signalée, raison en infobulle
        if obj_type == itemType.ANALYSE and getattr(obj, 'error', None):
            if role == Qt.ItemDataRole.DisplayRole and col == 0:
                return f"{obj.display_name} ⚠"
            if role == Qt.ItemDataRole.ToolTipRole:
                return f"Analyse non recalculée : {obj.error}"
        # modèle thermique : puissance utilisée pour Rth (voie ou valeur saisie)
        if (obj_type == itemType.ANALYSE and role == Qt.ItemDataRole.ToolTipRole
                and hasattr(getattr(obj, "results", None), "power")):
            return power_text(obj.results)

        # voie calculée : ƒ, formule en infobulle, échec du calcul signalé
        if obj_type == itemType.RAW and getattr(obj, "is_computed", False):
            if role == Qt.ItemDataRole.DisplayRole and col == 0:
                return f"ƒ {obj.name}" + (" ⚠" if obj.error else "")
            if role == Qt.ItemDataRole.ToolTipRole:
                tip = f"{obj.name} = {obj.formula}"
                if obj.error:
                    tip += f"\nCalcul impossible : {obj.error}"
                if obj.warnings:
                    tip += "\n" + "\n".join(obj.warnings)
                return tip

        # fichier : nom + point de fonctionnement, chemin en infobulle
        if obj_type == itemType.FILE:
            if role == Qt.ItemDataRole.DisplayRole and col == 0:
                return f"{obj.name} — {obj.label}" if obj.label else obj.name
            if role == Qt.ItemDataRole.ToolTipRole:
                return obj.address

        if role == Qt.ItemDataRole.DisplayRole and col == 0:
            if obj_type in (itemType.ANALYSE, itemType.FILTER):
                return obj.display_name
            else:
                return obj.name

        # ---------------- colonne 1 : valeur au curseur ----------------
        if role == Qt.ItemDataRole.DisplayRole and col == 1:
            if obj_type == itemType.RAW:
                if self.cursor_x is None:
                    return "-"

                val=self.cursor_values.get(obj)

                if isinstance(val, (float, np.floating)):
                    return f"{val:.2f}{obj.unit}"
                else:
                    return "-"

        #actualisation de la police pour les signaux sélectionnés (en gras)
        if role == Qt.ItemDataRole.FontRole:
            if  obj.is_selected:
                font = QFont()
                font.setBold(True)
                return font

        if role == Qt.ItemDataRole.ForegroundRole:
            if isinstance(obj, SignalObject) and obj.is_reference:
                return QBrush(QColor("#D32F2F"))  # rouge profond
            else:
                return QBrush(QColor("#000000"))  # noir profond

    # ---------------- Checkbox ----------------
        if (role == Qt.ItemDataRole.CheckStateRole and (obj_type == itemType.DERIVED or
            obj_type == itemType.RAW) and col == 0):
            return Qt.CheckState.Checked if obj.visible else Qt.CheckState.Unchecked

    # ---------------- Background color ----------------
        if role == Qt.ItemDataRole.BackgroundRole:
            if obj_type == itemType.RAW:
                # Couleur de fond = couleur du signal
                color = QColor(obj.pen.color())
                # léger alpha pour rester lisible
                color.setAlpha(150)
                return QBrush(color)

        # Icône uniquement sur la colonne 0
        if role == Qt.ItemDataRole.DecorationRole and col == 0:

            # FileObject
            if obj_type == itemType.FILE:
                return self.icon_file

            # SignalObject
            if obj_type == itemType.RAW:

                if obj.is_reference:
                    return self.icon_signal_reference
                elif obj.is_modified:
                    return self.icon_signal_modified
                else:
                    return self.icon_signal_raw

            # FilterNode
            if obj_type == itemType.FILTER:
                return self.icon_filter

        return None

    def updateCursorVal(self,x):

        #MAJ de la colonne value / on peut envisager une version où la colonne serait  déplaçable
        self.cursor_x=x

        # valeur de chaque voie APRÈS filtres, à l'instant x de SON axe des temps (une voie
        # peut être décalée dans le temps) ; recherche dichotomique, à chaque mouvement de
        # la souris
        self.cursor_values = {  sig: sig.nearest_value(x)
                                for file in self.workspace.files
                                for sig in file.signals}

        tl = self.index(0, 1, QModelIndex())
        br = self.index(self.rowCount(QModelIndex()) - 1, 1, QModelIndex())
        self.dataChanged.emit(tl, br, [Qt.ItemDataRole.DisplayRole])


    # ---------------------- Checkbox handling ----------------------

    def setData(self, index, value, role):
        if not index.isValid():
            return False

        item = index.internalPointer()
        obj = item.obj
        obj_type = obj.item_type

        if obj_type == itemType.RAW and role == Qt.ItemDataRole.CheckStateRole:
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

        obj = index.internalPointer().obj
        flags = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled

        if isinstance(obj, SignalObject):
            flags |= Qt.ItemFlag.ItemIsUserCheckable

        return flags


    # ---------------------- Update pipeline (undo/redo) ----------------------
    # Les enfants d'un signal sont ordonnés : les filtres (ordre de sig.pipeline)
    # PUIS les analyses (ordre de sig.analyses). La ligne d'un node dans l'arbre est
    # donc calculée à partir du signal (source de vérité) et de l'id du node, jamais
    # à partir de l'index transmis par la commande.

    def _node_row(self, sig: SignalObject, node) -> int:
        if node.item_type == itemType.FILTER:
            return sig.get_filter_index_by_id(node.id)
        return len(sig.pipeline) + sig.get_analysis_index_by_id(node.id)

    @staticmethod
    def _derived_of(sig: SignalObject, analysis) -> list:
        """Signaux dérivés produits par une analyse (liés par metadata['analysis_id'])."""
        return [ds for ds in sig.derived_signals
                if getattr(ds, 'metadata', {}).get('analysis_id') == analysis.id]

    def _make_node_item(self, sig: SignalObject, node, parent: TreeItem) -> TreeItem:
        item = TreeItem(node, parent = parent)
        if node.item_type == itemType.ANALYSE:
            for derived in self._derived_of(sig, node):
                item.add_child(TreeItem(derived, parent = item))
        return item

    def insert_node(self, sig: SignalObject, node: FilterNode | AnalysisNode):
        """
        Ajoute un filtre ou une analyse dans l'arbre. À appeler APRÈS l'insertion
        du node dans sig.pipeline / sig.analyses.
        """
        signal_item = self.find_signal_item(sig)
        if signal_item is None:
            return

        row  = self._node_row(sig, node)
        item = self._make_node_item(sig, node, signal_item)

        self.beginInsertRows(self.index_from_item(signal_item), row, row)
        signal_item.insert_child(row, item)
        self.endInsertRows()

        self.emit_node_event(ActionModifier.ADD_ACTION, item)

    def remove_node(self, sig: SignalObject, node: FilterNode | AnalysisNode):
        """Retire un filtre ou une analyse (et ses signaux dérivés) de l'arbre."""
        signal_item = self.find_signal_item(sig)
        if signal_item is None:
            return
        item = self.find_item_by_object_id(node.id, signal_item)
        if item is None:
            return

        row = item.row()
        self.beginRemoveRows(self.index_from_item(signal_item), row, row)
        signal_item.children.pop(row)
        self.endRemoveRows()

        # le node n'existe plus : le contexte émis est celui du signal parent
        self.emit_node_event(ActionModifier.REMOVE_ACTION, signal_item)

    def _rebuild_derived_items(self, sig: SignalObject, item: TreeItem, analysis):
        """Enfants d'une ligne d'analyse = ses signaux dérivés actuels."""
        index = self.index_from_item(item)
        if item.children:
            self.beginRemoveRows(index, 0, len(item.children)-1)
            item.children.clear()
            self.endRemoveRows()
        derived = self._derived_of(sig, analysis)
        if derived:
            self.beginInsertRows(index, 0, len(derived)-1)
            for ds in derived:
                item.add_child(TreeItem(ds, parent = item))
            self.endInsertRows()

    def refresh_object(self, obj):
        """Libellé d'un élément modifié (ex: étiquette d'un fichier)."""
        item = self.find_item(self.root, obj)
        if item is None:
            return
        index = self.index_from_item(item)
        # tous les rôles : libellé, case à cocher (visibilité changée ailleurs)...
        self.dataChanged.emit(index, index.siblingAtColumn(self.columnCount(index) - 1))

    def update_derived(self, sig: SignalObject, analysis):
        """
        Analyse recalculée automatiquement (données d'entrée modifiées) ou en échec :
        mise à jour de ses signaux dérivés et de son libellé. Pas de node_event : la
        sélection et le ParameterTree ne changent pas.
        """
        signal_item = self.find_signal_item(sig)
        if signal_item is None:
            return
        item = self.find_item_by_object_id(analysis.id, signal_item)
        if item is None:
            return
        self._rebuild_derived_items(sig, item, analysis)
        index = self.index_from_item(item)
        self.dataChanged.emit(index, index, [Qt.ItemDataRole.DisplayRole,
                                             Qt.ItemDataRole.ToolTipRole])

    def replace_node(self, sig: SignalObject, old_node, new_node):
        """
        Remplace un node par sa version modifiée (nodes immutables : modifier un
        paramètre crée un nouveau node, avec un nouvel id).
        """
        signal_item = self.find_signal_item(sig)
        if signal_item is None:
            return
        item = self.find_item_by_object_id(old_node.id, signal_item)
        if item is None:
            return

        item.obj = new_node
        index = self.index_from_item(item)

        if new_node.item_type == itemType.ANALYSE:
            # les signaux dérivés ont été recalculés : on reconstruit les enfants
            self._rebuild_derived_items(sig, item, new_node)

        self.dataChanged.emit(  index,
                                index,
                                [Qt.ItemDataRole.DisplayRole,
                                Qt.ItemDataRole.DecorationRole])
        self.emit_node_event(ActionModifier.MODIFY_ACTION, item)


    # ---------------------- Search ----------------------

    

    def find_item(self, item: TreeItem, target_obj):

        if item.obj is target_obj:
            return item
        for child in item.children:
            found = self.find_item(child, target_obj)
            if found:
                return found
        return None

    def find_item_by_object_id(self, obj_id, root_item=None):
        if obj_id is None:
            return None

        if root_item is None:
            root_item = self.root

        if getattr(root_item.obj, "id", None) == obj_id:
            return root_item

        for child in root_item.children:
            found = self.find_item_by_object_id(obj_id, child)
            if found is not None:
                return found

        return None

    def find_signal_item(self, signal):
        return self.find_item_by_object_id(signal.id)

    def signal_index(self, signal) -> QModelIndex:
        """
        Index Qt (colonne 0) d'un signal, calculé à la demande : toujours cohérent
        avec l'arbre (fichiers supprimés, rechargement...). QModelIndex() invalide
        si le signal n'est pas (ou plus) dans l'arbre.
        """
        item = self.find_signal_item(signal)
        if item is None:
            return QModelIndex()
        return self.index_from_item(item)

    def iter_signal_indexes(self):
        """(SignalObject, QModelIndex) des signaux bruts présents dans l'arbre."""
        for file_item in self.root.children:
            for sig_item in file_item.children:
                yield sig_item.obj, self.index_from_item(sig_item)

    def find_filter_item(self, signal, filter_id):
        signal_item = self.find_signal_item(signal)

        if signal_item is None:
            return None

        return self.find_item_by_object_id(filter_id, signal_item)

    def find_analysis_item(self, signal, analysis_id):
        signal_item = self.find_signal_item(signal)

        if signal_item is None:
            return None

        return self.find_item_by_object_id(analysis_id, signal_item)
