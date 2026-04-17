
# model/tree_item.py

class TreeItem:
    """
    Représente un nœud dans l'arborescence du modèle Qt.

    data peut être :
        - FileObject
        - SignalObject
        - FilterNode
    """

    def __init__(self, data, parent=None):
        self.data = data
        self.parent = parent
        self.children = []

    def add_child(self, item):
        self.children.append(item)
        item.parent = self

    def child(self, row):
        return self.children[row]

    def child_count(self):
        return len(self.children)

    def row(self):
        if self.parent is None:
            return 0
        return self.parent.children.index(self)
