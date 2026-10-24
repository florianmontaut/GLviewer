
# model/tree_item.py
from ressources.custom_types import itemType
from PyQt6.QtCore import Qt, QModelIndex

class TreeItem:
    """
    Représente un nœud dans l'arborescence du modèle Qt.

    data peut être :
        - FileObject
        - SignalObject
        - FilterNode
    """

    def __init__(self, data, parent=None):
        self.obj = data #! changer data par obj! et parent par parent_item
        self.parent_item = parent
        if isinstance(data,str):
            self.item_type = itemType.ROOT
        else:
            self.item_type = data.item_type
        self.children = []

    def add_child(self, item):
        self.children.append(item)
        item.parent_item = self

    def insert_child(self,index, item):
        self.children.insert(index,item)
        item.parent_item = self

    def child(self, row):
        
        if row < 0 or row >= len(self.children):
            return None
        return self.children[row]


    def child_count(self):
        return len(self.children)

    def row(self):
        if self.parent_item is None:
            return 0
        try:
            return self.parent_item.children.index(self)
        except ValueError:
            return -1

    # ------------------------------------------------------------------
    # Object helpers
    # ------------------------------------------------------------------

    @property
    def role(self):
        return getattr(self.obj, "item_type", None)

    @property
    def node_id(self):
        return getattr(self.obj, "id", None)

    @property
    def is_signal(self):
        return self.role in (itemType.RAW, itemType.DERIVED)

    @property
    def is_filter(self):
        return self.role == itemType.FILTER

    @property
    def is_analysis(self):
        return self.role == itemType.ANALYSE

    # ------------------------------------------------------------------
    # Parent signal resolution
    # ------------------------------------------------------------------

    def parent_signal_item(self):
        item = self

        while item is not None:
            if item.is_signal:
                return item

            item = item.parent_item

        return None

    @property
    def signal(self):
        signal_item = self.parent_signal_item()

        if signal_item is None:
            return None

        return signal_item.obj

    @property
    def action_signal(self):
        """
        Signal visé par les actions du menu (filtre, analyse, référence...) quand cette
        ligne est sélectionnée : le signal lui-même, ou le signal parent d'un filtre,
        d'une analyse ou d'un signal dérivé (qui ne se filtre pas). Permet d'enchaîner
        les actions sans resélectionner la voie.
        """
        sig = self.signal
        return getattr(sig, "parent_signal", sig)

    @property
    def filter_id(self):
        if not self.is_filter:
            return None
        return self.node_id

    @property
    def analysis_id(self):
        if not self.is_analysis:
            return None
        return self.node_id

    # ------------------------------------------------------------------
    # SelectionContext conversion
    # ------------------------------------------------------------------

    def to_selection_context(self):
        """
        Convertit ce TreeItem en SelectionContext.

        Import local volontaire pour éviter une boucle d'import :
        custom_items importe TreeItem pour typer SelectionContext.
        """
        from ressources.custom_items import SelectionContext

        if self.item_type == itemType.FILE:
            # paramètres du fichier (décalage, troncatures) : le contexte porte le FileObject
            return SelectionContext(role=itemType.FILE, signal=self.obj, item=self)

        signal = self.signal

        if signal is None:
            return None

        if self.is_filter:
            return SelectionContext(
                role=itemType.FILTER,
                signal=signal,
                filter_id=self.filter_id,
                item=self
            )

        if self.is_analysis:
            return SelectionContext(
                role=itemType.ANALYSE,
                signal=signal,
                analysis_id=self.analysis_id,
                item=self
            )

        if self.is_signal:
            return SelectionContext(
                role=self.role,
                signal=signal,
                item=self
            )

        return None
