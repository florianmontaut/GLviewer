
# controller/graph_controller.py

import numpy as np
from PyQt6 import QtCore,QtGui,QtWidgets
import pyqtgraph as pg
import pyqtgraph.parametertree as ptree
from model.base_objects import SignalObject,DerivedSignalObject
from model.missing_data import display_values
from ressources import custom_graph_functions,custom_types,custom_items,custom_menu

from controller.graph_context_menu_controller import GraphContextMenu
from controller.graph_option_controller import GraphTreeController

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


class RangePicker(QtCore.QObject):
    """
    Sélection interactive d'une plage temporelle sur le graphique, avant la création
    d'un modèle : une zone (LinearRegionItem) dont les deux bornes sont déplaçables.
        - Entrée ou double-clic dans la zone : validation  -> accepted(signal, t_start, t_end)
        - Échap                               : annulation  -> cancelled(signal)
    Une seule sélection à la fois : en démarrer une nouvelle annule la précédente.
    """

    accepted    = QtCore.pyqtSignal(object, float, float)
    cancelled   = QtCore.pyqtSignal(object)

    HINT = "Placez les bornes du modèle : Entrée ou double-clic pour valider, Échap pour annuler"

    def __init__(self, plot: pg.PlotItem, shortcut_parent: QtWidgets.QWidget):
        super().__init__()
        self.plot = plot
        self.shortcut_parent = shortcut_parent
        self.region = None
        self.signal = None
        self._shortcuts = []
        self.plot.scene().sigMouseClicked.connect(self._on_mouse_clicked)

    @property
    def is_active(self) -> bool:
        return self.region is not None

    def start(self, signal, t_start: float, t_end: float, bounds=None):
        """Affiche la zone [t_start, t_end] (bornes limitées à bounds=(min,max))."""
        if self.is_active:
            self.cancel()
        self.signal = signal
        color = signal.pen.color() if signal.pen is not None else QtGui.QColor('r')
        brush = QtGui.QColor(color)
        brush.setAlpha(40)
        self.region = pg.LinearRegionItem(  values      = (t_start, t_end),
                                            orientation = 'vertical',
                                            brush       = brush,
                                            bounds      = bounds,
                                            swapMode    = 'sort')
        self.region.setZValue(20)
        for line in self.region.lines:
            line.setPen(pg.mkPen(color, width=2))
            pg.InfLineLabel(line, text='{value:0.0f}s', position=0.95,
                            color=color, fill=(255,255,255,180))
        self.plot.addItem(self.region, ignoreBounds=True)

        # raccourcis actifs uniquement pendant la sélection
        for keys, slot in ( (QtCore.Qt.Key.Key_Return,  self.accept),
                            (QtCore.Qt.Key.Key_Enter,   self.accept),
                            (QtCore.Qt.Key.Key_Escape,  self.cancel)):
            shortcut = QtGui.QShortcut(QtGui.QKeySequence(keys), self.shortcut_parent)
            shortcut.setContext(QtCore.Qt.ShortcutContext.WindowShortcut)
            shortcut.activated.connect(slot)
            self._shortcuts.append(shortcut)

    def current_range(self) -> tuple[float, float]:
        t_start, t_end = self.region.getRegion()
        return float(t_start), float(t_end)

    def accept(self):
        if not self.is_active:
            return
        signal = self.signal
        t_start, t_end = self.current_range()
        self._stop()
        self.accepted.emit(signal, t_start, t_end)

    def cancel(self):
        if not self.is_active:
            return
        signal = self.signal
        self._stop()
        self.cancelled.emit(signal)

    def _stop(self):
        for shortcut in self._shortcuts:
            shortcut.setEnabled(False)
            shortcut.deleteLater()
        self._shortcuts = []
        self.plot.removeItem(self.region)
        self.region = None
        self.signal = None

    def _on_mouse_clicked(self, ev):
        if not self.is_active or not ev.double():
            return
        x = self.plot.vb.mapSceneToView(ev.scenePos()).x()
        t_start, t_end = self.current_range()
        if t_start <= x <= t_end:
            ev.accept()
            # différé : on ne retire pas la zone du graphique pendant son propre événement
            QtCore.QTimer.singleShot(0, self.accept)


class GraphController(QtCore.QObject):
    """
    Gère l'affichage PyQtGraph :
    - création courbes
    - update visibilité
    - update style
    - update pipeline (sig.y recalcule automatiquement)
    """

    curve_selected          = QtCore.pyqtSignal(custom_items.SelectionContext)
    reference_requested     = QtCore.pyqtSignal(SignalObject)
    cursor_moved_X          = QtCore.pyqtSignal(float)
    # case « snap to selected signal » du curseur souris (outils graphiques)
    snap_toggled            = QtCore.pyqtSignal(bool)
    menu_actions_triggered  = QtCore.pyqtSignal(    custom_types.ActionModifier,
                                                    custom_types.qSignalType,
                                                    object)

    def __init__(self, graph_widget : pg.GraphicsLayoutWidget, graphtree : ptree ,**opts):
        super().__init__()
        self.graph = graph_widget
        self.graph_tree = graphtree
        self.time_axis = RelativeTimeAxis(orientation='bottom')
        self.curves = {}  # SignalObject → PlotDataItem

        self.old_highlight          = None
        self.reference_sig          = None
        self.macro_recording        = False
        self.vcursor                = None
        self.xp_axis                = None
        self.yp_axis                = None
        self._mouse_pos             = QtCore.QPointF(0,0)

        # options par défaut de l'objet, le premier init est réalisé
        # par le menu_controller
        self.opts = {

        "X_title"              : "Temps",
        "X_unit"               : "s",
        "X_major_t"            : 1200,
        "X_minor_t"            : 300,
        "X_grid"               : True,
        "Y_title"              : "Temperature",
        "Y_unit"               : "°C",
        "Y_major_t"            : 10,
        "Y_minor_t"            : 2,
        "Y_grid"               : True,
        "update_selected"      : True,
        "downsample"           : True,
        "downsample_ratio"     : 10,
        "downsample_type"      : "peak",
        "background_color"     :"#FFFFFF",
        "dark_mode"            : False,
        # données manquantes (NaN) : interruption de la courbe ou valeur de remplacement
        "missing_display"      : self.MISSING_GAP,
        "missing_value"        : -20.0,
        }


        if opts:
            self.updateOptions(**opts)
        self._init_graph()
        self._init_graph_menu()
        self._init_cursor()
        # sélection de la plage des données d'entrée d'un modèle
        self.range_picker = RangePicker(self.plot, self.graph)
        # position (scene) du dernier clic droit dans le graphique : position des actions
        # du menu contextuel (ex: ajout de texte)
        self._context_scene_pos = None
        self.plot.scene().sigMouseClicked.connect(self._remember_context_click)

    # option « Missing data > Display » (Options > Graph settings)
    MISSING_GAP = "Gap in the curve"

    @property
    def missing_placeholder(self) -> float | None:
        """Valeur affichée à la place des données manquantes (None : courbe interrompue)."""
        if self.opts.get("missing_display", self.MISSING_GAP) == self.MISSING_GAP:
            return None
        return float(self.opts.get("missing_value", -20.0))

    def _display_y(self, sig):
        """Ordonnées tracées : données du signal, données manquantes selon l'option."""
        return display_values(sig.y, self.missing_placeholder)

    @property
    def mouse_pos(self):
        return self._mouse_pos #x = float(mouse_point.x())


    #! à revoir, en l'état si le fichier .JSON n'est pas conforme, ça peut planter le graph_ctrl
    #! peut-être faire une validation plus poussée dans le menu_controller avant d'appeler updateOptions
    def updateOptions(self,opts=None):
        missing_before = self.missing_placeholder
        if opts is not None:
            self.opts.update(opts)
        if self.missing_placeholder != missing_before:
            # affichage des données manquantes modifié : toutes les courbes redessinées
            for sig, curve in self.curves.items():
                curve.setData(sig.x, self._display_y(sig))
            self.update_vbox()

        if self.opts["downsample"]:
            self.plot.setDownsampling(mode=self.opts["downsample_type"],
                                            ds=self.opts["downsample_ratio"])

        if self.xp_axis is None:
            self.xp_axis = self.plot.getAxis('bottom')

        self.xp_axis.setLabel(text = self.opts["X_title"], units = self.opts["X_unit"])
        xticks = [self.opts["X_major_t"], self.opts["X_minor_t"]]
        self.xp_axis.setTickSpacing(xticks[0],xticks[1])

        if self.yp_axis is None:
            self.yp_axis = self.plot.getAxis('left')

        self.yp_axis.setLabel(text=self.opts["Y_title"], units = self.opts["Y_unit"])
        yticks = [self.opts["Y_major_t"],self.opts["Y_minor_t"]]
        self.yp_axis.setTickSpacing(yticks[0], yticks[1])
        self.graph.setBackground(self.opts["background_color"])
        self.plot.showGrid(x = self.opts["X_grid"], y = self.opts["Y_grid"],alpha = 0.4)
        # options complètes (opts peut n'en contenir qu'une partie)
        self.graph_tree_ctrl.update_settings(self.opts)


    def _init_graph(self):

        self.plot = pg.PlotItem(None,axisItems={"bottom"   : self.time_axis,
                                                "left"     : AdaptiveAxisItem('left')})
        self.graph.addItem(self.plot)
        # seuls les points visibles (plus une marge) sont décimés et dessinés : sans cela,
        # zoomer réduit la décimation sur TOUTE la courbe (1 million de points redessinés
        # pour un fichier .txt de NTC enregistré à 1 Hz)
        self.plot.setClipToView(True)
        if self.opts["downsample"]:
            self.plot.setDownsampling(mode=self.opts["downsample_type"],
                                            ds=self.opts["downsample_ratio"])
        #if self.xp_axis is None:
            self.xp_axis = self.plot.getAxis('bottom')
        #self.xp_axis.setLabel(text = self.opts["X_title"], units = self.opts["X_unit"])
        #xticks = [self.opts["X_major_t"], self.opts["X_minor_t"]]
        #self.xp_axis.setTickSpacing(xticks[0],xticks[1])
        #self.xp_axis.enableAutoSIPrefix(False)
        if self.yp_axis is None:
            self.yp_axis = self.plot.getAxis('left')
        self.yp_axis.setLabel(text=self.opts["Y_title"], units = self.opts["Y_unit"])
        yticks = [self.opts["Y_major_t"],self.opts["Y_minor_t"]]
        #self.yp_axis.setTickSpacing(yticks[0], yticks[1])

        self.yp_axis.enableAutoSIPrefix(False)
        self.plot.setMouseEnabled(x = True, y = True)
        self.graph.setBackground(self.opts["background_color"])
        self.plot.showGrid(x = self.opts["X_grid"], y = self.opts["Y_grid"],alpha = 0.4)
        self.legend = pg.LegendItem((80,60), offset = (70,20),colCount = 2,verSpacing = -5)
        self.vb = self.plot.vb
        self.plot.plot()
        self.vb.autoRange()

    def start_range_selection(self, sig: SignalObject):
        """
        Affiche la zone de sélection de plage sur le signal sig, pré-placée sur 10 %-90 %
        de la partie visible du signal et bornée à ses données.
        """
        x = sig.x
        data_min, data_max = float(x[0]), float(x[-1])
        view_min, view_max = self.vb.viewRange()[0]
        low, high = max(view_min, data_min), min(view_max, data_max)
        if high <= low:
            # signal hors de la vue : on se cale sur l'ensemble du signal
            low, high = data_min, data_max
        span = high - low
        self.range_picker.start(sig, low + 0.1*span, high - 0.1*span,
                                bounds=(data_min, data_max))

    def update_vbox(self):
        self.update_zoom_limits()
        self.vb.autoRange()

    # ----------------------------------------------------
    # Limites de zoom
    # ----------------------------------------------------

    # dézoom maximal : marge autour des courbes visibles, en part de leur étendue
    # (0.25 de chaque côté : la plage maximale vaut 1.5 fois l'étendue des données)
    ZOOM_OUT_MARGIN = 0.25

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
            y = np.asarray(self._display_y(sig), dtype=float)
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

    # ----------------------------------------------------
    def add_signal_curve(self, sig: SignalObject|DerivedSignalObject):

        if sig not in self.curves.keys():
            curve = SignalCurveItem(sig.x, self._display_y(sig), pen=sig.pen)
            # voie décochée (HZ détectée à l'import, choix sauvegardé dans le projet...)
            curve.setVisible(sig.visible)
            curve.setCurveClickable(True)
            curve.sigClicked.connect(self._on_curve_clicked)
            self.plot.addItem(curve)
            self.curves[sig] = curve
            self.update_zoom_limits()

    def _signal_from_curve(self, curve):
        for sig, c in self.curves.items():
            if c is curve:
                return sig
        return None

    def _on_curve_clicked(self,curve,event):
        sig = self._signal_from_curve(curve)
        self.highlight(sig)
        #print(f'signal: {sig.display_name}')
        if isinstance(sig, DerivedSignalObject):
            # une courbe dérivée sélectionne l'analyse qui l'a produite (arbre +
            # paramètres de l'analyse dans le ParameterTree)
            ctx = custom_items.SelectionContext(
                                    role=custom_items.itemType.ANALYSE,
                                    signal=sig.parent_signal,
                                    analysis_id=sig.metadata.get('analysis_id'),
                                    item=None,  # pas de TreeItem ici
                                )

        elif isinstance(sig, SignalObject):
            ctx = custom_items.SelectionContext(
                                    role=custom_items.itemType.RAW,
                                    signal=sig,
                                    item=None,
                                )
        else:
            #print(f'failed: {sig} / {type(sig)}')
            return  # sécurité
        """try:
            print(  "Graph_controller ligne 193: _on_curve_clicked => méthode appelée en cliquant sur une courbe: \n"+
                f'Signal: {ctx.signal.display_name}, role: {ctx.role}, filter index: {ctx.filter_index}'+
                f', Analysis index: {ctx.analysis_index}, derived index: {ctx.derived_index}\n')
        except:
            print('failed : échec d\'impression de données du CTX (Graph_controller)\n')"""
        self.curve_selected.emit(ctx)

    # ----------------------------------------------------
    def update_signal(self, sig):
        """Redessine la courbe après pipeline update."""
        if sig not in self.curves:
            return
        curve = self.curves[sig]
        curve.setData(sig.x, self._display_y(sig))
        # la courbe sélectionnée reste mise en évidence
        self._apply_curve_pen(sig, highlighted = sig is self.old_highlight)
        curve.setVisible(sig.visible)
        self.update_vbox()

    def freeze_updates(self, freeze: bool):
        self.graph.setUpdatesEnabled(not freeze)
        self.vb.enableAutoRange(False)
        if not freeze:
            self.update_vbox()
            self.vb.enableAutoRange(True)
            self.vb.autoRange()

    def select_graph_from_context(self,ctx:custom_items.SelectionContext):

        self.highlight(ctx.signal)

    def highlight(self, sig):
        """
        Met en surbrillance le signal sélectionné (largeur doublée, au premier plan) et
        rend son aspect normal à la courbe précédemment mise en évidence.
        La largeur de référence est toujours celle de sig.pen : pas de calcul à partir
        de la largeur actuelle de la courbe, qui peut avoir été réappliquée entre-temps
        (update_signal) ou appartenir à une courbe retirée (signal dérivé recalculé).
        """
        old = self.old_highlight
        if old is not None and old is not sig and old in self.curves:
            self._apply_curve_pen(old, highlighted=False)
        self.old_highlight = None

        if sig not in self.curves:
            # pas de courbe sélectionnée (ex: fichier) : curseur souris non accroché
            self._update_cursor_color(None)
            return
        curve = self.curves[sig]
        self._update_cursor_color(curve)
        self.on_selection_changed(sig)
        self._apply_curve_pen(sig, highlighted=True)
        self.old_highlight = sig

    def _apply_curve_pen(self, sig, highlighted: bool):
        """Applique sig.pen à sa courbe, avec une largeur doublée si highlighted."""
        pen = QtGui.QPen(sig.pen)
        if highlighted:
            # largeur 0 = trait cosmétique de 1 px
            pen.setWidthF(max(sig.pen.widthF(), 1.0) * 2)
        curve = self.curves[sig]
        curve.setPen(pen)
        curve.setZValue(10 if highlighted else 0)

    def remove_signal_curve(self, signal):
        curve = self.curves.pop(signal, None)
        if signal is self.old_highlight:
            self.old_highlight = None
        if curve is not None:

            self.plot.removeItem(curve)
            curve.setParentItem(None)
            curve.deleteLater()
            self.update_zoom_limits()
            #self.plot.removeItem(curve) #crash intempestif lors des undo/redo

    def _init_cursor(self):

        self.graph_tree_ctrl = GraphTreeController(self.plot,self.graph_tree,**self.opts)
        self.proxy = pg.SignalProxy(self.plot.scene().sigMouseMoved,rateLimit = 50,
                                    slot = self._on_mouse_moved)
        self.graph_tree_ctrl.mouseCursor.param('snap to selected signal').sigValueChanged.connect(
                                    lambda param, value: self.snap_toggled.emit(bool(value)))


    def _update_cursor_color(self,curve):
        """Couleur du curseur souris : celle de la courbe sélectionnée (si accroché)."""
        self.graph_tree_ctrl.mouseCursor.setCurve(curve)


    def _setup_mouse_guard(self):

        self._mouse_active = False
        self.plot.scene().sigMouseMoved.connect(self._on_mouse_moved)
        self.plot.scene().sigMouseClicked.connect(self._on_scene_mouse_clicked)


    def _on_scene_mouse_clicked(self, ev):
        pos = ev.scenePos()

        if self.vb.sceneBoundingRect().contains(pos):
            # clic dans le graphe
            if ev.button() == QtCore.Qt.MouseButton.LeftButton:
                self._mouse_active = True
                ev.accept()
                return
            elif ev.button() == QtCore.Qt.MouseButton.RightButton:
                self._mouse_active = False
                ev.accept()
                return
        else:
            # clic hors graphe
            self._mouse_active = False

    def _on_mouse_moved(self, ev):
        # Garde 2: souris sur le viewbox ?
        pos = ev[0]
        if  self.vb.sceneBoundingRect().contains(pos):

            mousePoint = self.vb.mapSceneToView(pos)
            # Y conservé pour le curseur libre (non accroché à une courbe)
            self._mouse_pos = mousePoint
            self.cursor_moved_X.emit(float(mousePoint.x()))

    #MAJ de la position du curseur grâce à la position de la souris
    def _update_cursor(self, x: float, y: float | None):

        if x is None:
            return
        if y is None:
            # curseur libre : il suit la souris
            y = float(self._mouse_pos.y())
        self.graph_tree_ctrl.mouseCursor.mouseUpdate(x,y)

    def _init_graph_menu(self):
        """
        méthode alembiqué mais permet de voir la technique de passage d'information
        via les slots et non pas via signals
        """
        self.menu = GraphContextMenu(
                                        self.plot,
                                        action_callback=self.actions_forwarding
                                    )
        self.on_selection_changed(None)

    def actions_forwarding(self, action_type, macro_name=None):
        """
        Route l'action demandée vers la bonne méthode métier
        """
        if action_type == custom_types.qSignalType.TEXT:
            self.add_text_annotation()
        else:
            self.menu_actions_triggered.emit(   custom_types.ActionModifier.ADD_ACTION,
                                                action_type,
                                                macro_name)

    # ----------------------------------------------------
    # Texte / annotations
    # ----------------------------------------------------

    # décalage (pixels) du texte d'une annotation par rapport au point annoté
    ANNOTATION_OFFSET = QtCore.QPointF(30, -30)

    def _remember_context_click(self, ev):
        """Mémorise la position du clic droit (ouverture du menu contextuel)."""
        if (ev.button() == QtCore.Qt.MouseButton.RightButton and
                self.vb.sceneBoundingRect().contains(ev.scenePos())):
            self._context_scene_pos = QtCore.QPointF(ev.scenePos())

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

    def add_text_annotation(self, scene_pos: QtCore.QPointF | None = None):
        """
        Ajoute un texte à la position du clic droit (scene_pos par défaut). Si une courbe
        visible est sélectionnée, le texte annote son échantillon le plus proche du clic :
        il est relié par une flèche et prérempli avec la valeur de l'échantillon.
        """
        if scene_pos is None:
            scene_pos = self._context_scene_pos
        if scene_pos is None:
            scene_pos = self.vb.sceneBoundingRect().center()

        sig = self.old_highlight
        sample = None
        if sig is not None and sig in self.curves and self.curves[sig].isVisible():
            sample = self.nearest_sample(sig, scene_pos)

        if sample is None:
            click = self.vb.mapSceneToView(scene_pos)
            return self.graph_tree_ctrl.addText(pos=(click.x(), click.y()))

        x, y = sample
        text_scene = self.vb.mapViewToScene(QtCore.QPointF(x, y)) + self.ANNOTATION_OFFSET
        text_pos = self.vb.mapSceneToView(text_scene)
        unit = getattr(sig, 'unit', '') or ''
        text = f"{sig.name}\n{y:.2f} {unit} @ {x:.0f} {self.opts['X_unit']}"
        return self.graph_tree_ctrl.addText(pos         = (text_pos.x(), text_pos.y()),
                                            anchor_pos  = (x, y),
                                            text        = text,
                                            color       = sig.pen.color())

    def on_selection_changed(self,sig:SignalObject=None):

        # actuellement seul un signal d'un même DataFrame peut servir de référence.
        if sig is not None:
            states = custom_menu.SelectionState(
                                        has_selection = True,
                                        has_reference = (self.reference_sig is not None and
                                                        not sig.is_reference) ,
                                        is_recording= self.macro_recording
                                        )
        else:
            states = custom_menu.SelectionState(
                                        has_selection = False,
                                        has_reference = False,
                                        is_recording= self.macro_recording
                                        )

        self.menu.update_enabled_states(states)


    def set_reference_signal(self, sig : SignalObject):

        self.reference_sig = sig