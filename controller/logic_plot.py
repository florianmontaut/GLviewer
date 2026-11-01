# controller/logic_plot.py
"""
Graphique des voies logiques (0 / 1, ex: voies logiques d'un enregistrement d'événement
FLXDrive) au-dessus du graphique principal, axe des temps commun :
    - une ligne par voie logique affichée, en escalier, compactée (une voie masquée ne
      laisse pas de vide), nom de la voie en graduation
    - valeur au curseur souris à gauche de chaque voie (1 en vert, 0 en rouge)
    - retiré du graphique quand aucune voie logique n'est affichée
Les courbes sont créées et suivies par le GraphController (dictionnaire curves) : seul
leur emplacement et leur tracé en escalier diffèrent des voies analogiques.
"""
import numpy as np
import pyqtgraph as pg
from PyQt6 import QtCore, QtGui


class LogicPlot:

    SPACING = 1.5           # écart vertical entre deux voies (une voie occupe 0..HEIGHT)
    HEIGHT = 1.0
    ROW_PIXELS = 22         # hauteur visée d'une voie
    ONE, ZERO, UNKNOWN = "#00A84F", "#D32F2F", "#808080"

    def __init__(self, layout: pg.GraphicsLayoutWidget, main_plot: pg.PlotItem):
        self.layout = layout
        self.main_plot = main_plot
        self.plot = pg.PlotItem()
        self.plot.setXLink(main_plot)
        self.plot.hideAxis('bottom')
        self.plot.setMouseEnabled(x=True, y=False)
        self.plot.enableAutoRange(y=False)
        self.plot.showGrid(x=True, y=False, alpha=0.3)
        self.plot.setClipToView(True)
        self.plot.setDownsampling(auto=True, mode='peak')
        self.plot.setMenuEnabled(False)
        self.plot.getAxis('left').setStyle(tickLength=0)
        self.cursor_line = pg.InfiniteLine(angle=90, movable=False,
                                           pen=pg.mkPen("#808080", width=1,
                                                        style=QtCore.Qt.PenStyle.DashLine))
        self.cursor_line.setVisible(False)
        self.plot.addItem(self.cursor_line, ignoreBounds=True)
        self.plot.vb.sigXRangeChanged.connect(self._place_values)

        self.signals = []           # voies logiques, dans l'ordre d'ajout
        self.curves = {}            # SignalObject -> courbe
        self.values = {}            # SignalObject -> TextItem (valeur au curseur)
        self.rows = {}              # SignalObject affiché -> rang (0 = en haut)
        self.cursor_x = None
        self.shown = False

    # ---------------- voies ----------------

    def add(self, sig, curve: pg.PlotDataItem):
        """Ajoute la courbe d'une voie logique (créée par le GraphController)."""
        self.signals.append(sig)
        self.curves[sig] = curve
        self.plot.addItem(curve)
        text = pg.TextItem("-", color=self.UNKNOWN, anchor=(0, 0.5))
        font = QtGui.QFont()
        font.setBold(True)
        text.setFont(font)
        self.plot.addItem(text, ignoreBounds=True)
        self.values[sig] = text
        self.relayout()

    def remove(self, sig):
        curve = self.curves.pop(sig, None)
        if curve is None:
            return
        self.signals.remove(sig)
        self.plot.removeItem(curve)
        self.plot.removeItem(self.values.pop(sig))
        self.relayout()

    def __contains__(self, sig):
        return sig in self.curves

    def step_data(self, sig, row: int):
        """Tracé en escalier de la voie au rang row : valeur tenue jusqu'à l'échantillon suivant."""
        x = np.asarray(sig.x, dtype=float)
        y = np.asarray(sig.y, dtype=float)
        if x.size == 0:
            return x, y
        base = self.base(row)
        x_step = np.repeat(x, 2)[1:]
        x_step = np.append(x_step, x[-1] + (x[-1] - x[-2] if x.size > 1 else 1.0))
        y_step = np.repeat(base + self.HEIGHT * y, 2)
        return x_step, y_step

    def base(self, row: int) -> float:
        """Ordonnée du 0 de la voie au rang row (rang 0 en haut)."""
        n = len(self.rows)
        return (n - 1 - row) * self.SPACING

    def relayout(self):
        """Rangs des voies affichées, tracés, graduations, place dans le graphique."""
        visible = [sig for sig in self.signals if sig.visible]
        self.rows = {sig: row for row, sig in enumerate(visible)}
        for sig in self.signals:
            curve = self.curves[sig]
            if sig in self.rows:
                curve.setData(*self.step_data(sig, self.rows[sig]))
            curve.setVisible(sig in self.rows)
            self.values[sig].setVisible(sig in self.rows)
        axis = self.plot.getAxis('left')
        axis.setTicks([[(self.base(row) + self.HEIGHT / 2, sig.name)
                        for sig, row in self.rows.items()]])
        n = len(self.rows)
        self.plot.setYRange(-0.4, max(n - 1, 0) * self.SPACING + self.HEIGHT + 0.4,
                            padding=0)
        self._show(n > 0)
        self._place_values()
        self.set_cursor(self.cursor_x)

    # ---------------- place dans le graphique ----------------

    def _show(self, show: bool):
        ci = self.layout.ci
        main_axis = self.main_plot.getAxis('left')
        if show and not self.shown:
            ci.removeItem(self.main_plot)
            ci.addItem(self.plot, row=0, col=0)
            ci.addItem(self.main_plot, row=1, col=0)
            self.shown = True
        elif not show and self.shown:
            ci.removeItem(self.plot)
            ci.removeItem(self.main_plot)
            ci.addItem(self.main_plot, row=0, col=0)
            ci.layout.setRowStretchFactor(1, 0)
            main_axis.setWidth(None)
            self.shown = False
        if not self.shown:
            return
        # hauteur selon le nombre de voies (hauteur maximale), partage égal au-delà : au
        # plus la moitié de la hauteur, quelle que soit la taille de la fenêtre
        self.plot.setMaximumHeight(len(self.rows) * self.ROW_PIXELS + 30)
        ci.layout.setRowStretchFactor(0, 1)
        ci.layout.setRowStretchFactor(1, 1)
        # axes gauches de même largeur : instants alignés entre les deux graphiques
        metrics = QtGui.QFontMetrics(self.plot.getAxis('left').style.get('tickFont')
                                     or QtGui.QFont())
        width = max([metrics.horizontalAdvance(sig.name) for sig in self.rows] + [0]) + 15
        width = max(width, 60)
        self.plot.getAxis('left').setWidth(width)
        main_axis.setWidth(width)

    # ---------------- curseur ----------------

    def set_cursor(self, x):
        """Ligne du curseur et valeur de chaque voie affichée à l'instant x."""
        self.cursor_x = x
        self.cursor_line.setVisible(x is not None and self.shown)
        if x is None:
            for text in self.values.values():
                text.setText("-")
                text.setColor(self.UNKNOWN)
            return
        self.cursor_line.setPos(x)
        for sig in self.rows:
            value = sig.nearest_value(x)
            text = self.values[sig]
            if value is None:
                text.setText("-")
                text.setColor(self.UNKNOWN)
            else:
                text.setText(f"{value:g}")
                text.setColor(self.ONE if value else self.ZERO)

    def _place_values(self, *_):
        """Valeurs au curseur au bord gauche de la zone affichée."""
        (x_min, x_max), _ = self.plot.vb.viewRange()
        x = x_min + 0.005 * (x_max - x_min)
        for sig, row in self.rows.items():
            self.values[sig].setPos(x, self.base(row) + self.HEIGHT / 2)
