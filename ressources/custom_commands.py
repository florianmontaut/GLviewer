
from PyQt6.QtGui import QUndoCommand

class ReplayableCommand(QUndoCommand):

    def to_descriptor(self):
        raise NotImplementedError
