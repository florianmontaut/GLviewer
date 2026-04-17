
from PyQt6.QtGui import QUndoCommand
from ressources.custom_items import ActionRequest

class Macro:

    def __init__(self, action_requests: list[ActionRequest],name=None):
        self.action_requests = action_requests
        self.name= name

    def apply(self, workspace_ctrl, signal):

        for action_request in self.action_requests:
            workspace_ctrl.push(signal, action_request)

class MacroCommand(QUndoCommand):

    def __init__(self, commands,text='Apply Macro'):
        super().__init__(text)
        self.commands = commands

    def redo(self):
        for cmd in self.commands:
            cmd.redo()

    def undo(self):
        for cmd in reversed(self.commands):
            cmd.undo()
