# view/detached_graph_window.py
"""
Fenêtre d'un graphique détaché de la fenêtre principale (GraphController.detach_panel).
La fermer réintègre le graphique à sa place dans la fenêtre principale ; elle est alors
masquée et servira au prochain graphique détaché : elle n'est jamais détruite avant la
fenêtre principale, sa scène reste donc valide pour les objets qui y ont été dessinés.
"""
import pyqtgraph as pg
from PyQt6 import QtCore, QtWidgets


class DetachedGraphWindow(QtWidgets.QWidget):

    # croix de la fenêtre : panneau à réintégrer
    closed = QtCore.pyqtSignal(object)

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent, QtCore.Qt.WindowType.Window)
        self.panel = None
        # ne retient pas l'application ouverte : elle se ferme avec la fenêtre principale
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_QuitOnClose, False)
        self.view = pg.GraphicsLayoutWidget()
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)
        self.resize(1000, 500)

    def assign(self, panel, title: str):
        self.panel = panel
        self.setWindowTitle(title)

    def release(self):
        """Plus de graphique : fenêtre masquée, en attente du prochain."""
        self.panel = None
        self.hide()

    def closeEvent(self, event):
        if self.panel is None:
            event.accept()
            return
        # fermeture refusée : le contrôleur réintègre le graphique et masque la fenêtre
        event.ignore()
        self.closed.emit(self.panel)
