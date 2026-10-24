# controller/benchmark_controller.py
import csv

import numpy as np
import pyqtgraph as pg
import pyqtgraph.exporters
from PyQt6 import QtCore, QtWidgets, sip

from model.benchmark import (QUANTITIES, benchmark_rows, channels_with_model, value)
from view.benchmark_window import BenchmarkWindow

ALL_MODELS = "Voies avec un modèle thermique"


class BenchmarkController(QtCore.QObject):
    """
    Fenêtre « Benchmark » : compare les modèles thermiques d'une même voie dans plusieurs
    essais. Le contenu suit le workspace (historique undo/redo, vue « Par voie »).
    """

    def __init__(self, workspace_getter, channel_model, parent_view=None):
        """
        Args:
            workspace_getter : callable() -> Workspace courant (il change au chargement
                               d'un projet)
            channel_model    : ChannelTreeModel (voies logiques et groupes)
        """
        super().__init__()
        self.workspace = workspace_getter
        self.channel_model = channel_model
        self.window = BenchmarkWindow(parent_view)
        self.rows = []
        self.channels = []
        for quantity in QUANTITIES:
            self.window.quantity_combo.addItem(f"{quantity.label} ({quantity.unit})")
        self.window.channels_combo.currentIndexChanged.connect(self._fill)
        self.window.quantity_combo.currentIndexChanged.connect(self._fill)
        self.window.export_csv_button.clicked.connect(self._export_csv_dialog)
        self.window.export_image_button.clicked.connect(self._export_image_dialog)
        channel_model.modelReset.connect(self.refresh)

    # ---------------- affichage ----------------

    def show(self):
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()
        self.refresh()

    @property
    def quantity(self):
        return QUANTITIES[max(self.window.quantity_combo.currentIndex(), 0)]

    def refresh(self, *_):
        """Liste des groupes et contenu (après toute modification du workspace)."""
        # fenêtre détruite avec la fenêtre principale (fermeture du logiciel)
        if sip.isdeleted(self.window) or not self.window.isVisible():
            return                                  # remis à jour à l'ouverture
        combo = self.window.channels_combo
        current = combo.currentData()
        with QtCore.QSignalBlocker(combo):
            combo.clear()
            combo.addItem(ALL_MODELS, None)
            for group in self.channel_model.user_groups():
                combo.addItem(f"Groupe {group.name}", group.id)
            found = combo.findData(current)
            combo.setCurrentIndex(found if found >= 0 else 0)
        self._fill()

    def _selected_channels(self):
        group_id = self.window.channels_combo.currentData()
        if group_id is None:
            return channels_with_model(self.channel_model.groups())
        group = next((g for g in self.channel_model.user_groups() if g.id == group_id), None)
        return list(group.channels) if group is not None else []

    def _fill(self, *_):
        self.channels = self._selected_channels()
        self.rows = benchmark_rows(self.workspace(), self.channels)
        self._fill_table()
        self._fill_plot()
        if not self.channels:
            self.window.info.setText("Aucune voie à comparer : appliquez un modèle thermique "
                                     "(« Get thermal model ») aux voies des essais.")
        else:
            self.window.info.setText("Point de fonctionnement : premier nombre de l'étiquette "
                                     "du fichier (ex: « 100 W »). Rth = ΔT / puissance du "
                                     "modèle thermique (paramètre du modèle, 100 W par défaut).")

    def _fill_table(self):
        table, quantity = self.window.table, self.quantity
        table.clear()
        table.setRowCount(len(self.rows))
        table.setColumnCount(len(self.channels) + 1)
        table.setHorizontalHeaderLabels(["Point de fonctionnement"]
                                        + [f"{c.name} ({quantity.unit})" for c in self.channels])
        table.setVerticalHeaderLabels([row.name for row in self.rows])
        for r, row in enumerate(self.rows):
            point = f"{row.x:g} {row.unit}".strip() if row.x is not None else "—"
            table.setItem(r, 0, QtWidgets.QTableWidgetItem(point))
            for c, channel in enumerate(self.channels, start=1):
                v = value(row, channel, quantity)
                item = QtWidgets.QTableWidgetItem("—" if v is None else f"{v:.4g}")
                item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignRight
                                      | QtCore.Qt.AlignmentFlag.AlignVCenter)
                model = row.models.get(channel)
                if model is None:
                    item.setToolTip("Pas de modèle thermique pour cette voie dans cet essai")
                else:
                    res = model.results
                    item.setToolTip(f"T∞ = {res.T_inf:.2f} °C, T0 = {res.T0:.2f} °C, "
                                    f"τ = {res.tau:.1f} s\nPuissance du modèle : "
                                    f"{model.get_param('power'):g} W")
                table.setItem(r, c, item)
        table.resizeColumnsToContents()

    def _abscissa(self):
        """Abscisses des essais (rang de l'essai si aucune étiquette n'a de nombre)."""
        if any(row.x is not None for row in self.rows):
            unit = next((row.unit for row in self.rows if row.x is not None and row.unit), "")
            label = f"Point de fonctionnement ({unit})" if unit else "Point de fonctionnement"
            return [row.x for row in self.rows], label
        return list(range(1, len(self.rows) + 1)), "Essai"

    def _fill_plot(self):
        plot, quantity = self.window.plot, self.quantity
        plot.clear()
        self.window.legend.clear()
        xs, x_label = self._abscissa()
        plot.setLabel("bottom", x_label)
        plot.setLabel("left", f"{quantity.label} ({quantity.unit})")
        for n, channel in enumerate(self.channels):
            points = [(x, value(row, channel, quantity)) for x, row in zip(xs, self.rows)]
            points = [(x, v) for x, v in points if x is not None and v is not None]
            if not points:
                continue
            color = pg.intColor(n, hues=max(len(self.channels), 9))
            x, y = np.array(points, dtype=float).T
            plot.plot(x, y, pen=pg.mkPen(color, width=2), symbol="o", symbolSize=8,
                      symbolBrush=color, name=channel.name)

    # ---------------- export ----------------

    def table_lines(self) -> list[list[str]]:
        """Tableau affiché (en-têtes compris), nombres avec une virgule décimale."""
        quantity = self.quantity
        lines = [["Essai", "Point de fonctionnement"]
                 + [f"{c.name} {quantity.label} ({quantity.unit})" for c in self.channels]]
        for row in self.rows:
            cells = [row.name, "" if row.x is None else f"{row.x:g}".replace(".", ",")]
            for channel in self.channels:
                v = value(row, channel, quantity)
                cells.append("" if v is None else f"{v:.6g}".replace(".", ","))
            lines.append(cells)
        return lines

    def export_csv(self, path):
        # séparateur ; et virgule décimale : ouverture directe dans Excel (français)
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            csv.writer(f, delimiter=";").writerows(self.table_lines())

    def export_image(self, path):
        exporter = pg.exporters.ImageExporter(self.window.plot.getPlotItem())
        exporter.parameters()["width"] = 1600
        exporter.export(str(path))

    def _export_csv_dialog(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self.window, "Exporter le tableau",
                                                        "benchmark.csv", "CSV (*.csv)")
        if path:
            self.export_csv(path)

    def _export_image_dialog(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self.window, "Exporter la courbe",
                                                        "benchmark.png", "PNG (*.png)")
        if path:
            self.export_image(path)
