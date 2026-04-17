
from PyQt6.QtWidgets import QTreeView
from PyQt6.QtCore import Qt, QModelIndex
from PyQt6.QtGui import QBrush, QColor

class CustomTreeView(QTreeView):
    """
    QTreeView :
    - clic gauche → sélection normale
    - clic droit → pas de sélection
    - clic droit → surbrillance temporaire de l'item sous le curseur
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._context_index: QModelIndex | None = None

    # -------------------------------------------------
    # Gestion souris
    # -------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            index = self.indexAt(event.position().toPoint())
            if index.isValid():
                self._set_context_highlight(index)
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            # la suppression finale se fait après le menu
            event.accept()
            return

        super().mouseReleaseEvent(event)

    # -------------------------------------------------
    # API surbrillance
    # -------------------------------------------------
    def _set_context_highlight(self, index: QModelIndex):
        # supprimer ancienne surbrillance
        self._clear_context_highlight()

        self._context_index = index

        # forcer redraw ciblé
        self.model().dataChanged.emit(
            index, index,
            [Qt.ItemDataRole.BackgroundRole]
        )

    def _clear_context_highlight(self):
        if self._context_index is not None:
            idx = self._context_index
            self._context_index = None
            self.model().dataChanged.emit(
                idx, idx,
                [Qt.ItemDataRole.BackgroundRole]
            )

    def clear_context_highlight(self):
        """À appeler explicitement après fermeture du menu"""
        self._clear_context_highlight()

    # -------------------------------------------------
    # Hook utilisé par le modèle
    # -------------------------------------------------
    def is_context_highlighted(self, index: QModelIndex) -> bool:
        return self._context_index == index
