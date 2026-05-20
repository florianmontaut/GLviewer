
from PyQt6.QtGui import QUndoCommand

class ReplayableCommand(QUndoCommand):

    def __init__(self,text=""):
        super().__init__(text)
        self.error = None

    def to_descriptor(self):
        raise NotImplementedError
