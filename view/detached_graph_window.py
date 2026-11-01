# view/detached_graph_window.py
"""
Fenêtre d'un graphique détaché de la fenêtre principale (GraphController.detach_panel).
La fermer réintègre le graphique à sa place dans la fenêtre principale.
"""
import pyqtgraph as pg
from PyQt6 import QtCore, QtWidgets


class DetachedGraphWindow(QtWidgets.QWidget):

    # fenêtre fermée par l'utilisateur : panneau à réintégrer
    closed = QtCore.pyqtSignal(object)

    def __init__(self, panel, title: str, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent, QtCore.Qt.WindowType.Window)
        self.panel = panel
        # ne retient pas l'application ouverte : elle se ferme avec la fenêtre principale
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_QuitOnClose, False)
        self.view = pg.GraphicsLayoutWidget()
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)
        self.setWindowTitle(title)
        self.resize(1000, 500)
        # fermeture demandée par le programme (réintégration, graphique retiré) : pas de
        # signal closed
        self._silent = False

    def close_silently(self):
        self._silent = True
        self.close()

    def closeEvent(self, event):
        if not self._silent:
            self.closed.emit(self.panel)
        super().closeEvent(event)
