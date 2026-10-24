
# controller/commands/remove_file.py
from PyQt6.QtGui import QUndoCommand


class RemoveFileCommand(QUndoCommand):
    """
    Retire un fichier de l'espace de travail (les données ne sont pas supprimées du
    disque). Le FileObject, ses filtres et ses analyses sont conservés pour l'undo, qui
    remet le fichier à sa place. Les mises à jour de l'arbre, du graphique et des analyses
    dépendantes sont faites par le contrôleur (MainController._detach_file / _attach_file).
    """

    def __init__(self, controller, file_obj):
        super().__init__(f"Remove file {file_obj.name}")
        self.controller = controller
        self.file_obj = file_obj
        self.index = controller.workspace.files.index(file_obj)
        # voie de référence (action « référence ») retirée avec le fichier
        self.removed_reference = None

    def redo(self):
        self.removed_reference = self.controller._detach_file(self.file_obj)

    def undo(self):
        self.controller._attach_file(self.file_obj, self.index, self.removed_reference)
