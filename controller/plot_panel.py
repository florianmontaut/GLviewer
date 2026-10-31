# controller/plot_panel.py
"""
Panneau de graphique : un tracé (PlotItem) avec son axe des temps, son axe vertical et
ses courbes. Le GraphController gère une liste de panneaux (un seul pour l'instant) ;
tout ce qui dépend d'un tracé particulier (courbes, limites de zoom, mise à l'échelle,
conversion écran -> données) est ici.
"""
import numpy as np
import pyqtgraph as pg
from PyQt6 import QtCore, QtGui

from ressources import theme


class RelativeTimeAxis(pg.DateAxisItem):
    #? faire de même pour l'axe Y ?
    def tickStrings(self, values, scale, spacing):
        labels = []
        for v in values:
            if spacing < 1:
                labels.append(f"{v*1000:.0f} ms")
            elif spacing < 60:
                labels.append(f"{v:.2f} s")
            elif spacing < 3600:
                labels.append(f"{v/60:.1f} min")
            elif spacing < 3600*24:
                labels.append(f"{v/3600:.1f} h")
            else:
                labels.append(f"{v/(3600*24):.1f} day")
        return labels


class SignalCurveItem(pg.PlotDataItem):
    """
    Courbe d'un signal. Avec clipToView, pyqtgraph ne dessine que la partie visible de
    la courbe, mais calcule aussi son étendue (mise à l'échelle automatique : chargement,
    « View all », bouton A) sur cette seule partie : la vue restait zoomée. L'étendue est
    ici calculée sur le jeu de données complet.
    """

    def dataBounds(self, ax, frac=1.0, orthoRange=None):
        if not self.curve.isVisible() or self._dataset is None:
            return super().dataBounds(ax, frac, orthoRange)
        if frac >= 1.0 and orthoRange is None:
            rect = self.dataRect()              # mis en cache par pyqtgraph
            if rect is None:
                return [None, None]
            return ([rect.left(), rect.right()] if ax == 0
                    else [rect.top(), rect.bottom()])

        x, y = self._dataset.x, self._dataset.y
        values, other = (x, y) if ax == 0 else (y, x)
        if orthoRange is not None:
            values = values[(other >= orthoRange[0]) & (other <= orthoRange[1])]
        values = values[np.isfinite(values)]
        if values.size == 0:
            return [None, None]
        if frac >= 1.0:
            return [float(values.min()), float(values.max())]
        low, high = np.percentile(values, [50 * (1 - frac), 50 * (1 + frac)])
        return [float(low), float(high)]


class AdaptiveAxisItem(pg.AxisItem):
    """
    Axe dont l'espacement des graduations choisi par l'utilisateur (setTickSpacing,
    ex: 10 °C / 2 °C) n'est appliqué que s'il donne un nombre raisonnable de graduations
    à l'écran ; au-delà (fort dézoom), pyqtgraph choisit un espacement adapté.
    Un espacement fixe sur une plage immense faisait calculer des millions de graduations
    (allocation de plusieurs Tio, application figée).
    """
    # nombre maximal de graduations principales affichées avec l'espacement utilisateur
    MAX_TICKS = 50

    def tickSpacing(self, minVal, maxVal, size):
        levels = self._tickSpacing
        if levels is not None:
            major = levels[0][0]
            if major > 0 and (maxVal - minVal) / major <= self.MAX_TICKS:
                return levels
            # espacement automatique de pyqtgraph
            self._tickSpacing = None
            try:
                return super().tickSpacing(minVal, maxVal, size)
            finally:
                self._tickSpacing = levels
        return super().tickSpacing(minVal, maxVal, size)


class PlotPanel:
    """
    Un tracé du graphique et ses courbes (signal -> SignalCurveItem).
        display_y : callable(signal) -> ordonnées tracées (données manquantes selon les
                    options du graphique, voir GraphController._display_y)
    """

    # dézoom maximal : marge autour des courbes visibles, en part de leur étendue
    # (0.25 de chaque côté : la plage maximale vaut 1.5 fois l'étendue des données)
    ZOOM_OUT_MARGIN = 0.25

    def __init__(self, display_y, opts: dict):
        self.display_y = display_y
        self.curves = {}                # SignalObject -> SignalCurveItem
        self.time_axis = RelativeTimeAxis(orientation='bottom')
        self.plot = pg.PlotItem(None, axisItems={"bottom": self.time_axis,
                                                 "left": AdaptiveAxisItem('left')})
        self.vb = self.plot.vb
        # seuls les points visibles (plus une marge) sont décimés et dessinés : sans cela,
        # zoomer réduit la décimation sur TOUTE la courbe (1 million de points redessinés
        # pour un fichier .txt de NTC enregistré à 1 Hz)
        self.plot.setClipToView(True)
        self._apply_downsampling(opts)
        self.xp_axis = self.plot.getAxis('bottom')
        self.yp_axis = self.plot.getAxis('left')
        self.yp_axis.setLabel(text=opts["Y_title"], units=opts["Y_unit"])
        self.yp_axis.enableAutoSIPrefix(False)
        self.plot.setMouseEnabled(x=True, y=True)
        self.plot.showGrid(x=opts["X_grid"], y=opts["Y_grid"], alpha=0.4)
        self.plot.plot()
        self.vb.autoRange()

    # ---------------- options ----------------

    def _apply_downsampling(self, opts):
        if opts["downsample"]:
            self.plot.setDownsampling(mode=opts["downsample_type"],
                                      ds=opts["downsample_ratio"])

    def apply_options(self, opts: dict):
        """Options du graphique (Options > Graph settings) : axes, graduations, grille."""
        self._apply_downsampling(opts)
        self.xp_axis.setLabel(text=opts["X_title"], units=opts["X_unit"])
        self.xp_axis.setTickSpacing(opts["X_major_t"], opts["X_minor_t"])
        self.yp_axis.setLabel(text=opts["Y_title"], units=opts["Y_unit"])
        self.yp_axis.setTickSpacing(opts["Y_major_t"], opts["Y_minor_t"])
        self.plot.showGrid(x=opts["X_grid"], y=opts["Y_grid"], alpha=0.4)

    def apply_theme(self, dark: bool):
        theme.style_plot(self.plot, dark)

    # ---------------- courbes ----------------

    def add_curve(self, sig, on_clicked) -> SignalCurveItem:
        curve = SignalCurveItem(sig.x, self.display_y(sig), pen=sig.pen)
        # voie décochée (HZ détectée à l'import, choix sauvegardé dans le projet...)
        curve.setVisible(sig.visible)
        curve.setCurveClickable(True)
        curve.sigClicked.connect(on_clicked)
        self.plot.addItem(curve)
        self.curves[sig] = curve
        self.update_zoom_limits()
        return curve

    def remove_curve(self, sig) -> bool:
        curve = self.curves.pop(sig, None)
        if curve is None:
            return False
        self.plot.removeItem(curve)
        curve.setParentItem(None)
        curve.deleteLater()
        self.update_zoom_limits()
        return True

    def redraw(self, sig):
        self.curves[sig].setData(sig.x, self.display_y(sig))

    def signal_of(self, curve):
        return next((sig for sig, c in self.curves.items() if c is curve), None)

    # ---------------- vue ----------------

    def autorange(self):
        self.update_zoom_limits()
        self.vb.autoRange()

    def contains(self, scene_pos) -> bool:
        """Point de l'écran (coordonnées de la scène) dans la zone de tracé ?"""
        return self.vb.sceneBoundingRect().contains(scene_pos)

    def update_zoom_limits(self):
        """
        Limites de zoom de la ViewBox calculées sur les courbes VISIBLES (voies, filtres,
        signaux dérivés : différence, projection d'un modèle...). Les voies masquées
        (ex: HZ) et les annotations n'interviennent pas.
            - dézoom maximal : étendue des courbes + ZOOM_OUT_MARGIN de chaque côté
            - zoom maximal   : quelques échantillons en X, 0.01 en Y
        Sans courbe visible, les limites précédentes sont conservées.
        """
        # étendue calculée sur les données elles-mêmes : ViewBox.childrenBounds() ajoute
        # une marge en pixels, convertie selon le zoom du moment (énorme quand la vue
        # est encore minuscule, au chargement)
        visible = [sig for sig, curve in self.curves.items()
                   if curve.isVisible() and len(sig.x) > 0]
        bounds = []
        for sig in visible:
            x = np.asarray(sig.x, dtype=float)
            # valeur de remplacement des données manquantes comprise : elle doit rester
            # visible
            y = np.asarray(self.display_y(sig), dtype=float)
            if np.isfinite(x).any() and np.isfinite(y).any():
                bounds.append((np.nanmin(x), np.nanmax(x), np.nanmin(y), np.nanmax(y)))
        if not bounds:
            return
        x0 = min(b[0] for b in bounds)
        x1 = max(b[1] for b in bounds)
        y0 = min(b[2] for b in bounds)
        y1 = max(b[3] for b in bounds)

        # pas d'échantillonnage le plus fin des courbes visibles
        steps = [np.min(np.diff(np.asarray(sig.x[:100], dtype=float)))
                 for sig in visible if len(sig.x) > 1]
        steps = [s for s in steps if np.isfinite(s) and s > 0]
        min_x_range = 10 * min(steps) if steps else 1e-3

        # étendue minimale : une courbe plate (ou un seul point) reste zoomable
        width_x = max(x1 - x0, min_x_range)
        width_y = max(y1 - y0, 1.0)
        margin_x, margin_y = self.ZOOM_OUT_MARGIN * width_x, self.ZOOM_OUT_MARGIN * width_y

        self.vb.setLimits(  xMin        = x0 - margin_x,
                            xMax        = x1 + margin_x,
                            yMin        = y0 - margin_y,
                            yMax        = y1 + margin_y,
                            minXRange   = min_x_range,
                            maxXRange   = width_x + 2 * margin_x,
                            minYRange   = 0.01,
                            maxYRange   = width_y + 2 * margin_y)

    def nearest_sample(self, sig, scene_pos: QtCore.QPointF) -> tuple[float, float] | None:
        """
        Échantillon (x, y) de sig le plus proche d'un point de l'écran. La distance est
        mesurée en pixels : un écart de 1 °C et un écart de 1 s n'ont pas le même poids
        selon le zoom.
        """
        x = np.asarray(sig.x, dtype=float)
        y = np.asarray(sig.y, dtype=float)
        if x.size == 0:
            return None
        target = self.vb.mapSceneToView(scene_pos)
        px_w, px_h = self.vb.viewPixelSize()
        distance = ((x - target.x()) / px_w)**2 + ((y - target.y()) / px_h)**2
        if np.all(np.isnan(distance)):
            return None
        i = int(np.nanargmin(distance))
        return float(x[i]), float(y[i])
