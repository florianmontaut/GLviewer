# controller/commands/graph_number.py
from PyQt6.QtGui import QUndoCommand


class GraphNumberCommand(QUndoCommand):
    """
    Graphique empilé de voies (paramètre « Graph » d'une voie, d'un fichier ou d'un
    groupe, glisser-déposer) : toutes les voies concernées en un seul Ctrl+Z.
    """

    def __init__(self, controller, signals, number: int):
        super().__init__(f"Move to graph {number}")
        self.controller = controller
        self.old = {sig: sig.graph_number for sig in signals}
        self.new = {sig: number for sig in signals}

    def redo(self):
        self.controller._apply_graph_numbers(self.new)

    def undo(self):
        self.controller._apply_graph_numbers(self.old)
