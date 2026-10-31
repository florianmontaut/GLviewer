# view/benchmark_window.py
import pathlib

import pyqtgraph as pg
from PyQt6 import QtCore, QtGui, QtWidgets

from ressources import theme

PATH = pathlib.Path(__file__).parent


class BenchmarkWindow(QtWidgets.QWidget):
    """
    Fenêtre « Benchmark » (menu Options) : tableau des résultats des modèles thermiques
    (une ligne par essai, une colonne par voie) et courbe résultat / point de
    fonctionnement. Rempli par BenchmarkController.
    """

    def __init__(self, parent=None):
        super().__init__(parent, QtCore.Qt.WindowType.Window)
        self.setWindowTitle("Benchmark")
        self.setWindowIcon(QtGui.QIcon(str(PATH / "icon.ico")))
        self.resize(1100, 600)

        self.channels_combo = QtWidgets.QComboBox()
        self.channels_combo.setToolTip("Voies comparées : celles ayant un modèle thermique, "
                                       "ou un groupe de la vue « Par voie »")
        self.quantity_combo = QtWidgets.QComboBox()
        self.export_csv_button = QtWidgets.QPushButton("Exporter le tableau (.csv)…")
        self.export_image_button = QtWidgets.QPushButton("Exporter la courbe (.png)…")

        controls = QtWidgets.QHBoxLayout()
        controls.addWidget(QtWidgets.QLabel("Voies :"))
        controls.addWidget(self.channels_combo, 1)
        controls.addWidget(QtWidgets.QLabel("Grandeur :"))
        controls.addWidget(self.quantity_combo)
        controls.addStretch()
        controls.addWidget(self.export_csv_button)
        controls.addWidget(self.export_image_button)

        self.table = QtWidgets.QTableWidget()
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.plot = pg.PlotWidget()
        self._apply_theme()
        self.plot.showGrid(x=True, y=True, alpha=0.3)
        self.legend = self.plot.addLegend()

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        splitter.addWidget(self.table)
        splitter.addWidget(self.plot)
        splitter.setSizes([500, 600])
        for index in range(2):
            splitter.setCollapsible(index, False)

        self.info = QtWidgets.QLabel()
        self.info.setWordWrap(True)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(controls)
        layout.addWidget(splitter, 1)
        layout.addWidget(self.info)

    def _apply_theme(self):
        """Graphique aux couleurs du thème courant."""
        self.plot.setBackground(theme.colors()["graph_bg"])
        theme.style_plot(self.plot.getPlotItem())

    def showEvent(self, event):
        # thème changé depuis la création de la fenêtre (option « Dark mode »)
        self._apply_theme()
        super().showEvent(event)
