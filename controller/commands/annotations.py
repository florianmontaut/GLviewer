
# controller/commands/annotations.py
"""
Commandes undo/redo des textes du graphique. Comme pour les filtres et les analyses,
la commande modifie le modèle (workspace.annotations) puis met à jour la vue
(GraphTreeController : show_annotation / remove_annotation).
"""
from PyQt6.QtGui import QUndoCommand

from model.annotations import TextAnnotation


class AddAnnotationCommand(QUndoCommand):

    def __init__(self, workspace, view, annotation: TextAnnotation):
        super().__init__("Add text")
        self.workspace  = workspace
        self.view       = view
        self.annotation = annotation

    def redo(self):
        self.workspace.annotations[self.annotation.id] = self.annotation
        self.view.show_annotation(self.annotation)

    def undo(self):
        self.workspace.annotations.pop(self.annotation.id, None)
        self.view.remove_annotation(self.annotation.id)


class RemoveAnnotationCommand(QUndoCommand):

    def __init__(self, workspace, view, annotation: TextAnnotation):
        super().__init__("Remove text")
        self.workspace  = workspace
        self.view       = view
        self.annotation = annotation

    def redo(self):
        self.workspace.annotations.pop(self.annotation.id, None)
        self.view.remove_annotation(self.annotation.id)

    def undo(self):
        self.workspace.annotations[self.annotation.id] = self.annotation
        self.view.show_annotation(self.annotation)


class ModifyAnnotationCommand(QUndoCommand):
    """Contenu modifié, texte ou point annoté déplacé (old et new ont le même id)."""

    def __init__(self, workspace, view, old: TextAnnotation, new: TextAnnotation):
        super().__init__("Modify text" if old.html != new.html else "Move text")
        self.workspace  = workspace
        self.view       = view
        self.old        = old
        self.new        = new

    def _apply(self, annotation):
        self.workspace.annotations[annotation.id] = annotation
        self.view.show_annotation(annotation)

    def redo(self):
        self._apply(self.new)

    def undo(self):
        self._apply(self.old)
