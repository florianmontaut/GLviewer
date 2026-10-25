# controller/commands/computed_channel.py
from PyQt6.QtGui import QUndoCommand


class AddComputedChannelCommand(QUndoCommand):
    """
    Ajoute une voie calculée (model.computed.ComputedSignal) à son fichier. Les mises à
    jour (arbre, graphique, vue « Par voie », voies qui en dépendent) sont faites par le
    contrôleur (MainController._attach_signal / _detach_signal).
    """

    def __init__(self, controller, sig, index: int | None = None):
        super().__init__(f"Add computed channel {sig.name}")
        self.controller = controller
        self.sig = sig
        self.index = len(sig.file.signals) if index is None else index

    def redo(self):
        self.controller._attach_signal(self.sig, self.index)

    def undo(self):
        self.controller._detach_signal(self.sig)


class RemoveComputedChannelCommand(AddComputedChannelCommand):
    """Supprime une voie calculée (remise à sa place par l'undo)."""

    def __init__(self, controller, sig):
        super().__init__(controller, sig, sig.file.signals.index(sig))
        self.setText(f"Remove computed channel {sig.name}")

    def redo(self):
        super().undo()

    def undo(self):
        super().redo()


class ModifyComputedChannelCommand(QUndoCommand):
    """Paramètres d'une voie calculée (formule, nom, unité, base de temps, couleur)."""

    def __init__(self, controller, sig, new_params: dict):
        super().__init__(f"Modify computed channel {sig.name}")
        self.controller = controller
        self.sig = sig
        self.old_params = {key: sig.get_param(key) for key in new_params}
        self.new_params = dict(new_params)

    def redo(self):
        self.controller._apply_signal_params(self.sig, self.new_params)

    def undo(self):
        self.controller._apply_signal_params(self.sig, self.old_params)
