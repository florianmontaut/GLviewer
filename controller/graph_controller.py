
# controller/graph_controller.py

import numpy as np
from PyQt6 import QtCore,QtGui,QtWidgets
import pyqtgraph as pg
import pyqtgraph.parametertree as ptree
from model.base_objects import SignalObject,DerivedSignalObject
from model.missing_data import display_values
from ressources import custom_graph_functions,custom_types,custom_items,custom_menu,theme

from controller.graph_context_menu_controller import GraphContextMenu
from controller.graph_option_controller import GraphTreeController
# axes et courbe : controller.plot_panel (noms conservés ici pour les imports existants)
from controller.plot_panel import (PlotPanel, RelativeTimeAxis, SignalCurveItem,
                                   AdaptiveAxisItem)

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

    Le graphique est fait de panneaux (controller.plot_panel.PlotPanel : un tracé, ses
    axes et ses courbes). Un seul panneau pour l'instant : plot, vb et curves sont ceux
    du panneau principal.
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
        self.panels = []  # PlotPanel ; le premier est le panneau principal

        self.old_highlight          = None
        self.reference_sig          = None
        self.macro_recording        = False
        self.vcursor                = None
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
            for panel in self.panels:
                for sig in panel.curves:
                    panel.redraw(sig)
            self.update_vbox()

        for panel in self.panels:
            panel.apply_options(self.opts)
        self._apply_theme()
        # options complètes (opts peut n'en contenir qu'une partie)
        self.graph_tree_ctrl.update_settings(self.opts)


    def _init_graph(self):
        self.add_panel()
        self.legend = pg.LegendItem((80,60), offset = (70,20),colCount = 2,verSpacing = -5)

    def add_panel(self) -> PlotPanel:
        """Nouveau panneau de graphique, sous les précédents."""
        panel = PlotPanel(self._display_y, self.opts)
        self.graph.addItem(panel.plot, row=len(self.panels), col=0)
        self.panels.append(panel)
        self._apply_theme()
        return panel

    # ---------------- panneau principal (compatibilité : un seul panneau) ----------------

    @property
    def main_panel(self) -> PlotPanel:
        return self.panels[0]

    @property
    def plot(self) -> pg.PlotItem:
        return self.main_panel.plot

    @property
    def vb(self) -> pg.ViewBox:
        return self.main_panel.vb

    @property
    def time_axis(self):
        return self.main_panel.time_axis

    @property
    def xp_axis(self):
        return self.main_panel.xp_axis

    @property
    def yp_axis(self):
        return self.main_panel.yp_axis

    @property
    def curves(self) -> dict:
        """Courbes de tous les panneaux : signal -> courbe."""
        if len(self.panels) == 1:
            return self.main_panel.curves
        return {sig: curve for panel in self.panels for sig, curve in panel.curves.items()}

    def panel_of(self, sig) -> PlotPanel | None:
        """Panneau où la courbe de sig est tracée."""
        return next((panel for panel in self.panels if sig in panel.curves), None)

    def panel_at(self, scene_pos) -> PlotPanel | None:
        """Panneau sous un point de l'écran (coordonnées de la scène)."""
        return next((panel for panel in self.panels if panel.contains(scene_pos)), None)

    def _apply_theme(self):
        """Fond (option « Graph Background color » ou celui du thème), axes et textes."""
        dark = theme.is_dark(self.opts.get("dark_mode", False))
        self.graph.setBackground(theme.graph_background(self.opts["background_color"], dark))
        for panel in self.panels:
            panel.apply_theme(dark)
        if getattr(self, "graph_tree_ctrl", None) is not None:
            self.graph_tree_ctrl.apply_theme(dark)

    def start_range_selection(self, sig: SignalObject):
        """
        Affiche la zone de sélection de plage sur le signal sig, pré-placée sur 10 %-90 %
        de la partie visible du signal et bornée à ses données.
        """
        x = sig.x
        data_min, data_max = float(x[0]), float(x[-1])
        view_min, view_max = (self.panel_of(sig) or self.main_panel).vb.viewRange()[0]
        low, high = max(view_min, data_min), min(view_max, data_max)
        if high <= low:
            # signal hors de la vue : on se cale sur l'ensemble du signal
            low, high = data_min, data_max
        span = high - low
        self.range_picker.start(sig, low + 0.1*span, high - 0.1*span,
                                bounds=(data_min, data_max))

    def update_vbox(self):
        for panel in self.panels:
            panel.autorange()

    # dézoom maximal (voir PlotPanel.update_zoom_limits)
    ZOOM_OUT_MARGIN = PlotPanel.ZOOM_OUT_MARGIN

    def update_zoom_limits(self):
        """Limites de zoom de chaque panneau, sur ses courbes visibles."""
        for panel in self.panels:
            panel.update_zoom_limits()

    # ----------------------------------------------------
    def add_signal_curve(self, sig: SignalObject|DerivedSignalObject, panel=None):
        """Courbe de sig, dans panel (par défaut le panneau principal)."""
        if self.panel_of(sig) is None:
            (panel or self.main_panel).add_curve(sig, self._on_curve_clicked)

    def _signal_from_curve(self, curve):
        for panel in self.panels:
            sig = panel.signal_of(curve)
            if sig is not None:
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
        panel = self.panel_of(sig)
        if panel is None:
            return
        panel.redraw(sig)
        # la courbe sélectionnée reste mise en évidence
        self._apply_curve_pen(sig, highlighted = sig is self.old_highlight)
        panel.curves[sig].setVisible(sig.visible)
        self.update_vbox()

    def freeze_updates(self, freeze: bool):
        self.graph.setUpdatesEnabled(not freeze)
        for panel in self.panels:
            panel.vb.enableAutoRange(False)
        if not freeze:
            self.update_vbox()
            for panel in self.panels:
                panel.vb.enableAutoRange(True)
                panel.vb.autoRange()

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
        if signal is self.old_highlight:
            self.old_highlight = None
        panel = self.panel_of(signal)
        if panel is not None:
            panel.remove_curve(signal)

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

        if self.panel_at(pos) is not None:
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
        panel = self.panel_at(pos)
        if panel is not None:

            mousePoint = panel.vb.mapSceneToView(pos)
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
                self.panel_at(ev.scenePos()) is not None):
            self._context_scene_pos = QtCore.QPointF(ev.scenePos())

    def nearest_sample(self, sig, scene_pos: QtCore.QPointF) -> tuple[float, float] | None:
        """Échantillon de sig le plus proche d'un point de l'écran (PlotPanel.nearest_sample)."""
        return (self.panel_of(sig) or self.main_panel).nearest_sample(sig, scene_pos)

    def add_text_annotation(self, scene_pos: QtCore.QPointF | None = None):
        """
        Ajoute un texte à la position du clic droit (scene_pos par défaut). Si une courbe
        visible est sélectionnée, le texte annote son échantillon le plus proche du clic :
        il est relié par une flèche et prérempli avec la valeur de l'échantillon.
        """
        if scene_pos is None:
            scene_pos = self._context_scene_pos
        if scene_pos is None:
            scene_pos = self.main_panel.vb.sceneBoundingRect().center()
        # textes : tracés dans le panneau principal (outils graphiques)
        vb = self.main_panel.vb

        sig = self.old_highlight
        sample = None
        if sig is not None and sig in self.curves and self.curves[sig].isVisible():
            sample = self.nearest_sample(sig, scene_pos)

        if sample is None:
            click = vb.mapSceneToView(scene_pos)
            return self.graph_tree_ctrl.addText(pos=(click.x(), click.y()))

        x, y = sample
        text_scene = vb.mapViewToScene(QtCore.QPointF(x, y)) + self.ANNOTATION_OFFSET
        text_pos = vb.mapSceneToView(text_scene)
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