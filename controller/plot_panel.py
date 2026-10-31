# controller/plot_panel.py
"""
Panneau de graphique : un tracé (PlotItem) avec son axe des temps, ses axes verticaux
(un par unité) et ses courbes. Le GraphController gère une liste de panneaux (un seul pour l'instant) ;
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


def curve_unit(sig) -> str:
    """Unité d'une courbe (« °C », « W »...) : chaque unité a son échelle verticale."""
    return str(getattr(sig, "unit", "") or "").strip()


class UnitScale:
    """
    Échelle verticale d'une unité secondaire d'un panneau : sa ViewBox (axe X lié à celle
    du panneau) et son axe à droite. Sa plage suit celle de l'échelle principale par une
    relation affine (y = a * y_principal + b) : zoomer ou déplacer le graphique déplace
    toutes les courbes ensemble ; glisser ou zoomer sur l'axe de droite change a et b.
    """

    def __init__(self, unit: str, main_vb: pg.ViewBox, parent: pg.PlotItem):
        self.unit = unit
        self.main_vb = main_vb
        self.axis = None
        self.a, self.b = 1.0, 0.0
        self.vb = pg.ViewBox(enableMenu=False)
        self.vb.setParentItem(parent)
        # sous la ViewBox principale : elle reçoit la souris (zoom, déplacement, menu)
        self.vb.setZValue(main_vb.zValue() - 1)
        self.vb.setMouseEnabled(x=False, y=True)
        self.vb.setXLink(main_vb)
        self.vb.setGeometry(main_vb.geometry())
        main_vb.sigResized.connect(self._sync_geometry)
        main_vb.sigYRangeChanged.connect(self._follow_main)
        self.vb.sigRangeChangedManually.connect(self.store_relation)

    def _sync_geometry(self):
        self.vb.setGeometry(self.main_vb.geometry())
        self.vb.linkedViewChanged(self.main_vb, self.vb.XAxis)

    def _follow_main(self):
        m0, m1 = self.main_vb.viewRange()[1]
        self.vb.setYRange(self.a * m0 + self.b, self.a * m1 + self.b, padding=0)

    def store_relation(self, *args):
        """Relation entre la plage de cette échelle et celle de l'échelle principale."""
        m0, m1 = self.main_vb.viewRange()[1]
        s0, s1 = self.vb.viewRange()[1]
        if m1 - m0 == 0:
            return
        self.a = (s1 - s0) / (m1 - m0)
        self.b = s0 - self.a * m0

    def fit(self, bounds: tuple[float, float] | None):
        """Plage ajustée aux données (bornes y0, y1), marge de 2 %."""
        if bounds is None:
            return
        y0, y1 = bounds
        margin = 0.02 * max(y1 - y0, 1e-9)
        self.vb.setYRange(y0 - margin, y1 + margin, padding=0)
        self.store_relation()

    def remove(self):
        self.main_vb.sigResized.disconnect(self._sync_geometry)
        self.main_vb.sigYRangeChanged.disconnect(self._follow_main)
        self.vb.setXLink(None)
        self.vb.setParentItem(None)
        scene = self.vb.scene()
        if scene is not None:
            scene.removeItem(self.vb)


class PlotPanel:
    """
    Un tracé du graphique et ses courbes (signal -> SignalCurveItem).
        display_y : callable(signal) -> ordonnées tracées (données manquantes selon les
                    options du graphique, voir GraphController._display_y)
    Une échelle verticale par unité : l'unité principale (celle des options du
    graphique, Y unit, si une courbe l'utilise, sinon la première) à gauche, chaque autre
    unité (UnitScale) sur un axe à droite.
    """

    # dézoom maximal : marge autour des courbes visibles, en part de leur étendue
    # (0.25 de chaque côté : la plage maximale vaut 1.5 fois l'étendue des données)
    ZOOM_OUT_MARGIN = 0.25

    def __init__(self, display_y, opts: dict):
        self.display_y = display_y
        self.opts = opts
        self.curves = {}                # SignalObject -> SignalCurveItem
        self.main_unit = None           # unité de l'axe de gauche
        self.scales = {}                # unité secondaire -> UnitScale (ordre des axes)
        self._extra_axes = []           # axes à droite au-delà du premier
        self._dark = None
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
        # courbes des échelles secondaires : hors du PlotItem, réglées une à une
        for sig, curve in self.curves.items():
            if self.unit_of(sig) != self.main_unit:
                self._configure_secondary(curve)

    def _configure_secondary(self, curve):
        curve.setDownsampling(*self.plot.downsampleMode())
        curve.setClipToView(self.plot.clipToViewMode())

    def apply_options(self, opts: dict):
        """Options du graphique (Options > Graph settings) : axes, graduations, grille."""
        self.opts = opts
        self._apply_downsampling(opts)
        self.xp_axis.setLabel(text=opts["X_title"], units=opts["X_unit"])
        self.xp_axis.setTickSpacing(opts["X_major_t"], opts["X_minor_t"])
        self.yp_axis.setTickSpacing(opts["Y_major_t"], opts["Y_minor_t"])
        self.plot.showGrid(x=opts["X_grid"], y=opts["Y_grid"], alpha=0.4)
        # l'unité principale peut changer (Y unit)
        self.update_units()

    def apply_theme(self, dark: bool):
        self._dark = dark
        theme.style_plot(self.plot, dark)
        c = theme.colors(dark)
        for axis in self._extra_axes:
            axis.setPen(pg.mkPen(c["graph_axis"]))
            axis.setTextPen(pg.mkPen(c["graph_text"]))

    # ---------------- unités ----------------

    def unit_of(self, sig) -> str:
        return curve_unit(sig)

    def units(self) -> list[str]:
        """Unités des courbes du panneau, l'unité principale en premier."""
        units = list(dict.fromkeys(self.unit_of(sig) for sig in self.curves))
        preferred = str(self.opts.get("Y_unit", "") or "").strip()
        if preferred in units:
            units.remove(preferred)
            units.insert(0, preferred)
        return units

    def view_of(self, sig) -> pg.ViewBox:
        """ViewBox où la courbe de sig est tracée (celle de son unité)."""
        unit = self.unit_of(sig)
        scale = self.scales.get(unit) if unit != self.main_unit else None
        return scale.vb if scale is not None else self.vb

    def update_units(self):
        """
        Échelles du panneau mises à jour selon les unités des courbes (courbe ajoutée,
        retirée, unité d'une voie modifiée, unité principale des options changée) : les
        courbes changent d'échelle si besoin, les échelles inutiles sont retirées.
        """
        units = self.units()
        main = units[0] if units else None
        secondary = units[1:]
        new_scales = [unit for unit in secondary if unit not in self.scales]
        for unit in new_scales:
            self.scales[unit] = UnitScale(unit, self.vb, self.plot)
        self.main_unit = main

        # courbes déplacées AVANT de retirer les échelles inutiles : une ViewBox retirée
        # est détruite avec les courbes qu'elle contient encore
        for sig, curve in self.curves.items():
            target = self.view_of(sig)
            current = curve.getViewBox()
            if current is target:
                continue
            if current is self.vb:
                self.plot.removeItem(curve)
            elif current is not None:
                current.removeItem(curve)
            # ViewBox.addItem passe la courbe dans la scène avant de la rattacher à la
            # ViewBox : clipToView chercherait la ViewBox (rétabli ci-dessous)
            curve.setClipToView(False)
            if target is self.vb:
                self.plot.addItem(curve)
            else:
                target.addItem(curve)
                self._configure_secondary(curve)
        for unit in [u for u in self.scales if u not in secondary]:
            self.scales.pop(unit).remove()
        # ordre des axes de droite : celui des unités
        self.scales = {unit: self.scales[unit] for unit in secondary}
        self._layout_axes()
        for unit in new_scales:
            self.scales[unit].fit(self._y_bounds(unit))

    def _layout_axes(self):
        """Axe de gauche à l'unité principale, un axe à droite par unité secondaire."""
        y_unit = str(self.opts.get("Y_unit", "") or "").strip()
        if self.main_unit is None or self.main_unit == y_unit:
            self.yp_axis.setLabel(text=self.opts["Y_title"], units=self.opts["Y_unit"])
        else:
            self.yp_axis.setLabel(text=self.main_unit)

        scales = list(self.scales.values())
        # axes supplémentaires : colonnes 3, 4... de la mise en page du PlotItem (la
        # colonne 2 est l'axe de droite du PlotItem)
        while len(self._extra_axes) < len(scales) - 1:
            axis = AdaptiveAxisItem('right')
            axis.enableAutoSIPrefix(False)
            self.plot.layout.addItem(axis, 2, 3 + len(self._extra_axes))
            self._extra_axes.append(axis)
        while len(self._extra_axes) > max(len(scales) - 1, 0):
            axis = self._extra_axes.pop()
            self.plot.layout.removeItem(axis)
            axis.setParentItem(None)
            if axis.scene() is not None:
                axis.scene().removeItem(axis)
        if self._dark is not None:
            self.apply_theme(self._dark)

        right = self.plot.getAxis('right')
        if scales:
            self.plot.showAxis('right')
            right.enableAutoSIPrefix(False)
        else:
            self.plot.hideAxis('right')
            right.linkToView(self.vb)
        for scale, axis in zip(scales, [right] + self._extra_axes):
            scale.axis = axis
            axis.linkToView(scale.vb)
            axis.setLabel(text=scale.unit)

    def _y_bounds(self, unit) -> tuple[float, float] | None:
        """Étendue verticale des courbes visibles d'une unité."""
        lows, highs = [], []
        for sig, curve in self.curves.items():
            if self.unit_of(sig) != unit or not curve.isVisible():
                continue
            y = np.asarray(self.display_y(sig), dtype=float)
            if np.isfinite(y).any():
                lows.append(np.nanmin(y))
                highs.append(np.nanmax(y))
        return (float(min(lows)), float(max(highs))) if lows else None

    # ---------------- courbes ----------------

    def add_curve(self, sig, on_clicked) -> SignalCurveItem:
        curve = SignalCurveItem(sig.x, self.display_y(sig), pen=sig.pen)
        # voie décochée (HZ détectée à l'import, choix sauvegardé dans le projet...)
        curve.setVisible(sig.visible)
        curve.setCurveClickable(True)
        curve.sigClicked.connect(on_clicked)
        self.curves[sig] = curve
        self.update_units()
        self.update_zoom_limits()
        return curve

    def remove_curve(self, sig) -> bool:
        curve = self.curves.pop(sig, None)
        if curve is None:
            return False
        view = curve.getViewBox()
        if view is self.vb:
            self.plot.removeItem(curve)
        elif view is not None:
            view.removeItem(curve)
        curve.setParentItem(None)
        curve.deleteLater()
        self.update_units()
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
        for unit, scale in self.scales.items():
            scale.fit(self._y_bounds(unit))

    def contains(self, scene_pos) -> bool:
        """Point de l'écran (coordonnées de la scène) dans la zone de tracé ?"""
        return self.vb.sceneBoundingRect().contains(scene_pos)

    def update_zoom_limits(self):
        """
        Limites de zoom de la ViewBox calculées sur les courbes VISIBLES de l'unité
        principale (voies, filtres, signaux dérivés : différence, projection d'un
        modèle...). Les voies masquées (ex: HZ) et les annotations n'interviennent pas ;
        les échelles secondaires suivent l'échelle principale.
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
            if self.unit_of(sig) != self.main_unit:
                continue
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
        # l'axe des temps couvre aussi les courbes des autres unités
        for sig in visible:
            x = np.asarray(sig.x, dtype=float)
            if np.isfinite(x).any():
                x0, x1 = min(x0, np.nanmin(x)), max(x1, np.nanmax(x))

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
        vb = self.view_of(sig)              # échelle de l'unité de la courbe
        target = vb.mapSceneToView(scene_pos)
        px_w, px_h = vb.viewPixelSize()
        distance = ((x - target.x()) / px_w)**2 + ((y - target.y()) / px_h)**2
        if np.all(np.isnan(distance)):
            return None
        i = int(np.nanargmin(distance))
        return float(x[i]), float(y[i])
