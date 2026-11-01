
# controller/graph_controller.py

import numpy as np
from PyQt6 import QtCore,QtGui,QtWidgets
import pyqtgraph as pg
import pyqtgraph.parametertree as ptree
from model.base_objects import (SignalObject, DerivedSignalObject, MAX_GRAPHS,
                                GRAPH_SIGNALS_MIME)
from model.missing_data import display_values
from ressources import custom_graph_functions,custom_types,custom_items,custom_menu,theme

from controller.graph_context_menu_controller import GraphContextMenu
from controller.graph_option_controller import GraphTreeController
from view.detached_graph_window import DetachedGraphWindow
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
        # tracé de la zone selon le signal (remplacé par le GraphController)
        self.plot_of = lambda signal: plot
        self._main_scene = self.plot.scene()
        self._main_scene.sigMouseClicked.connect(self._on_mouse_clicked)

    @property
    def is_active(self) -> bool:
        return self.region is not None

    def start(self, signal, t_start: float, t_end: float, bounds=None):
        """Affiche la zone [t_start, t_end] (bornes limitées à bounds=(min,max))."""
        if self.is_active:
            self.cancel()
        self.signal = signal
        # panneau du signal (graphiques empilés)
        self.plot = self.plot_of(signal)
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
            # toute fenêtre de l'application : la zone peut être dans un graphique détaché
            shortcut.setContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
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

    def _on_mouse_clicked(self, ev, scene=None):
        """Double-clic dans la zone : validation (scene : scène du clic, par défaut celle
        de la fenêtre principale)."""
        if not self.is_active or not ev.double():
            return
        if (scene or self._main_scene) is not self.plot.scene():
            return
        x = self.plot.vb.mapSceneToView(ev.scenePos()).x()
        t_start, t_end = self.current_range()
        if t_start <= x <= t_end:
            ev.accept()
            # différé : on ne retire pas la zone du graphique pendant son propre événement
            QtCore.QTimer.singleShot(0, self.accept)


class PanelSplitter(QtWidgets.QGraphicsObject):
    """
    Poignée entre deux graphiques empilés (index et index + 1) : glisser pour répartir
    leur hauteur, double-clic pour donner la même hauteur à tous les graphiques.
    """
    HEIGHT = 8

    def __init__(self, graph_ctrl, index: int):
        super().__init__()
        self.graph_ctrl = graph_ctrl
        self.index = index
        self._rect = QtCore.QRectF()
        self._hover = False
        # au-dessus des graphiques : reçoit la souris avant la ViewBox (pas de déplacement
        # de la vue)
        self.setZValue(1e5)
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(QtCore.Qt.MouseButton.LeftButton)
        self.setCursor(QtCore.Qt.CursorShape.SplitVCursor)
        self.setToolTip("Glisser : hauteur des graphiques ; double-clic : hauteurs égales")

    def boundingRect(self):
        return self._rect

    def place(self, rect: QtCore.QRectF):
        self.prepareGeometryChange()
        self._rect = rect
        self.update()

    def paint(self, painter, option, widget=None):
        if self._hover:
            color = QtGui.QColor(theme.colors()["accent"])
            color.setAlpha(90)
            painter.fillRect(self._rect, color)

    def hoverEnterEvent(self, ev):
        self._hover = True
        self.update()

    def hoverLeaveEvent(self, ev):
        self._hover = False
        self.update()

    def mousePressEvent(self, ev):
        ev.accept()

    def mouseMoveEvent(self, ev):
        self.graph_ctrl.drag_splitter(self.index, ev.scenePos().y())

    def mouseReleaseEvent(self, ev):
        self.graph_ctrl.heights_changed.emit(self.graph_ctrl.heights())

    def mouseDoubleClickEvent(self, ev):
        ev.accept()
        self.graph_ctrl.reset_heights()


class GraphDropTarget(QtCore.QObject):
    """
    Dépôt sur le graphique de voies glissées depuis un arbre (GRAPH_SIGNALS_MIME) :
    numéro du graphique visé, ou nouveau graphique sous le dernier. Dans la fenêtre d'un
    graphique détaché (panel), toujours ce graphique.
    """

    def __init__(self, graph_ctrl, view=None, panel=None):
        super().__init__(view if view is not None else graph_ctrl)
        self.graph_ctrl = graph_ctrl
        self.panel = panel
        view = view if view is not None else graph_ctrl.graph
        self.view = view
        view.setAcceptDrops(True)
        view.viewport().setAcceptDrops(True)
        view.viewport().installEventFilter(self)

    def eventFilter(self, obj, event):
        kind = event.type()
        if kind not in (QtCore.QEvent.Type.DragEnter, QtCore.QEvent.Type.DragMove,
                        QtCore.QEvent.Type.Drop, QtCore.QEvent.Type.DragLeave):
            return False
        if kind == QtCore.QEvent.Type.DragLeave:
            self._show(None)
            return False
        if not event.mimeData().hasFormat(GRAPH_SIGNALS_MIME):
            return False
        if self.panel is not None:
            number = self.graph_ctrl.number_of_panel(self.panel)
        else:
            number = self.graph_ctrl.graph_number_at(
                            self.view.mapToScene(event.position().toPoint()))
        if kind == QtCore.QEvent.Type.Drop:
            self._show(None)
            ids = bytes(event.mimeData().data(GRAPH_SIGNALS_MIME)).decode().split(",")
            self.graph_ctrl.signals_dropped.emit(ids, number)
        else:
            self._show(number)
        event.setDropAction(QtCore.Qt.DropAction.LinkAction)
        event.accept()
        return True

    def _show(self, number):
        # cadre du graphique visé : fenêtre principale seulement
        if self.panel is None:
            self.graph_ctrl.show_drop_target(number)


class GraphController(QtCore.QObject):
    """
    Gère l'affichage PyQtGraph :
    - création courbes
    - update visibilité
    - update style
    - update pipeline (sig.y recalcule automatiquement)

    Le graphique est fait de panneaux empilés (controller.plot_panel.PlotPanel : un
    tracé, ses axes et ses courbes), à l'axe des temps commun. Chaque voie est tracée dans
    le panneau de son paramètre « Graph » (graph_number, 1 : celui du haut) ; il y a autant
    de panneaux que le plus grand numéro utilisé par une courbe ou un texte. plot, vb et
    time_axis sont ceux du panneau principal (le premier).
    """

    curve_selected          = QtCore.pyqtSignal(custom_items.SelectionContext)
    reference_requested     = QtCore.pyqtSignal(SignalObject)
    cursor_moved_X          = QtCore.pyqtSignal(float)
    # voies (id) déposées sur le graphique n° (glisser-déposer depuis un arbre)
    signals_dropped         = QtCore.pyqtSignal(list, int)
    # hauteurs relatives des graphiques réglées par l'utilisateur (poignées)
    heights_changed         = QtCore.pyqtSignal(list)
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
        # graphique actif : celui du dernier signal sélectionné (outils graphiques,
        # recalage dans le temps)
        self._active_panel = None
        # hauteurs relatives souhaitées des graphiques (1 : hauteur moyenne) ; peut
        # contenir plus de valeurs que de graphiques affichés (projet relu)
        self._heights = []
        self._splitters = []
        # texte affiché à la place des graphiques quand ils sont tous détachés
        self._placeholder = None

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
        # zone tracée dans le panneau du signal
        self.range_picker.plot_of = self.plot_of
        # position (scene) du dernier clic droit dans le graphique : position des actions
        # du menu contextuel (ex: ajout de texte)
        self._context_scene_pos = None
        self._context_scene = None
        self.plot.scene().sigMouseClicked.connect(self._remember_context_click)
        # voies glissées depuis un arbre
        self._drop_frame = None
        self.drop_target = GraphDropTarget(self)
        # fenêtre principale fermée : graphiques détachés réintégrés (fenêtres fermées)
        main_window = self.graph.window()
        if hasattr(main_window, "closing"):
            main_window.closing.connect(self.attach_all)

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
        """Nouveau panneau de graphique, sous les précédents, à l'axe des temps commun."""
        panel = PlotPanel(self._display_y, self.opts)
        # dernier des graphiques de la fenêtre principale
        self._show_placeholder(False)
        self.graph.addItem(panel.plot, row=len(self.attached_panels()), col=0)
        if self.panels:
            panel.vb.setXLink(self.main_panel.vb)
            if getattr(self, "menu", None) is not None:
                self._share_menu(panel)
        self._add_detach_action(panel)
        self.panels.append(panel)
        panel.plot.geometryChanged.connect(self._place_splitters)
        self._layout_panels()
        self._apply_theme()
        return panel

    def _share_menu(self, panel):
        """
        Actions du menu contextuel (filtre, modèle, texte...) aussi dans ce panneau : ce
        sont les mêmes QAction (états activé / désactivé communs), placées avant
        « View All » comme dans le menu du panneau principal.
        """
        main_menu = self.main_panel.vb.menu
        actions = main_menu.actions()
        shared = actions[:actions.index(main_menu.viewAll)]
        panel.vb.menu.insertActions(panel.vb.menu.viewAll, shared)

    def _remove_panel(self, panel):
        if self.graph_tree_ctrl.mouseCursor.graph is panel.plot:
            self.graph_tree_ctrl.mouseCursor.set_graph(self.plot)
        if self.range_picker.is_active and self.range_picker.plot is panel.plot:
            self.range_picker.cancel()
        self.panels.remove(panel)
        if self._active_panel is panel:
            self._active_panel = None
        self.graph_tree_ctrl.set_graph(self.active_panel.plot)
        panel.plot.geometryChanged.disconnect(self._place_splitters)
        panel.dispose()
        if panel.window is not None:
            # graphique détaché devenu vide : sa fenêtre est fermée
            window, panel.window = panel.window, None
            window.view.removeItem(panel.plot)
            self._release_scene(window.view.scene())
            window.close_silently()
            window.deleteLater()
        else:
            self.graph.removeItem(panel.plot)
        self._reset_free_rows()
        self._layout_panels()

    @property
    def active_panel(self) -> PlotPanel:
        """Graphique du dernier signal sélectionné (le principal par défaut)."""
        if self._active_panel not in self.panels:
            self._active_panel = self.main_panel
        return self._active_panel

    def _sync_active_panel(self):
        """
        Graphique actif = celui de la courbe sélectionnée (s'il y en a une ; sinon le
        dernier) : les curseurs des outils graphiques y sont déplacés.
        """
        sig = self.old_highlight
        panel = self.panel_of(sig) if sig is not None else None
        if panel is not None:
            self._active_panel = panel
        tools = getattr(self, "graph_tree_ctrl", None)
        if tools is not None:
            tools.set_graph(self.active_panel.plot)

    def _layout_panels(self):
        """
        Titre de l'axe des temps sous le dernier panneau seulement, hauteurs des panneaux,
        une poignée entre deux panneaux.
        """
        attached = self.attached_panels()
        for panel in self.panels:
            # graphique détaché : titre de l'axe des temps dans sa fenêtre
            panel.xp_axis.showLabel(panel.window is not None or panel is attached[-1])
        self._show_placeholder(not attached)
        self._apply_heights()
        scene = self.graph.scene()
        count = max(len(attached) - 1, 0)
        while len(self._splitters) > count:
            scene.removeItem(self._splitters.pop())
        while len(self._splitters) < count:
            splitter = PanelSplitter(self, len(self._splitters))
            scene.addItem(splitter)
            self._splitters.append(splitter)
        self._place_splitters()

    # ---------------- graphiques détachés ----------------

    def attached_panels(self) -> list:
        """Graphiques de la fenêtre principale, dans l'ordre."""
        return [panel for panel in self.panels if panel.window is None]

    def _add_detach_action(self, panel):
        """Menu contextuel du graphique : « Détacher » / « Réintégrer »."""
        menu = panel.vb.menu
        menu.addSeparator()
        panel.detach_action = QtGui.QAction("Detach graph", menu)
        panel.detach_action.triggered.connect(lambda _=False, p=panel: self.toggle_detach(p))
        menu.addAction(panel.detach_action)

    def toggle_detach(self, panel):
        if panel.window is None:
            self.detach_panel(panel)
        else:
            self.attach_panel(panel)

    def detach_panel(self, panel):
        """
        Graphique déplacé dans sa propre fenêtre (le graphique principal aussi : la
        fenêtre principale affiche alors un texte à la place des graphiques).
        """
        if panel not in self.panels or panel.window is not None:
            return
        number = self.number_of_panel(panel)
        self.graph.removeItem(panel.plot)
        window = DetachedGraphWindow(panel, f"Graph {number} - GLviewer", self.graph.window())
        panel.window = window
        window.view.addItem(panel.plot, row=0, col=0)
        self._connect_scene(window.view.scene())
        GraphDropTarget(self, window.view, panel)
        window.closed.connect(self.attach_panel)
        panel.detach_action.setText("Reattach graph")
        self._relayout()
        self._apply_theme()
        window.show()

    def attach_panel(self, panel):
        """Graphique détaché réintégré à sa place dans la fenêtre principale."""
        window = panel.window
        if window is None:
            return
        panel.window = None
        window.closed.disconnect(self.attach_panel)
        old_scene = window.view.scene()
        window.view.removeItem(panel.plot)
        # fermeture déjà en cours (croix de la fenêtre) : sans effet
        window.close_silently()
        panel.detach_action.setText("Detach graph")
        self._relayout()
        self._apply_theme()
        # tracé de retour dans la fenêtre principale : ses textes oublient la scène de la
        # fenêtre, détruite ensuite
        self._release_scene(old_scene)
        window.deleteLater()

    def _release_scene(self, scene):
        """
        Textes (annotations, étiquettes des curseurs...) détachés de la scène d'une
        fenêtre qui va être détruite, où qu'ils soient maintenant (fenêtre principale,
        autre fenêtre détachée). pyqtgraph (TextItem.paint) se déconnecte de la scène
        précédente au dessin suivant : si elle est déjà détruite, erreur.
        """
        scenes = {id(s): s for s in [self.graph.scene(), scene] + [
                    p.window.view.scene() for p in self.panels if p.window is not None]}
        items = [item for living in scenes.values() for item in living.items()]
        # curseurs des outils graphiques masqués : hors de toute scène
        tools = self.graph_tree_ctrl
        for tool_item in (tools.mouseCursor.cursors + [tools.mouseCursor.valtext]
                          + tools.cursors_H.cursors + tools.cursors_V.cursors):
            items += [tool_item] + tool_item.childItems()
        for item in items:
            if (not isinstance(item, pg.TextItem)
                    or getattr(item, "_lastScene", None) is not scene):
                continue
            try:
                scene.sigPrepareForPaint.disconnect(item.updateTransform)
            except (TypeError, RuntimeError):
                pass
            item._lastScene = None

    def attach_all(self):
        """Tous les graphiques réintégrés (fermeture de la fenêtre principale)."""
        for panel in list(self.panels):
            self.attach_panel(panel)

    def _relayout(self):
        """Graphiques de la fenêtre principale replacés dans l'ordre de leur numéro."""
        layout = self.graph.ci
        self._show_placeholder(False)
        for panel in self.panels:
            if panel.plot in layout.items:
                layout.removeItem(panel.plot)
        for row, panel in enumerate(self.attached_panels()):
            layout.addItem(panel.plot, row=row, col=0)
        self._reset_free_rows()
        self._layout_panels()

    def _reset_free_rows(self):
        """Lignes de la mise en page sans graphique : plus de place réservée."""
        layout = self.graph.ci.layout
        for row in range(len(self.attached_panels()), len(self.panels) + 2):
            layout.setRowStretchFactor(row, 0)

    def _show_placeholder(self, show: bool):
        """Texte à la place des graphiques quand ils sont tous détachés."""
        layout = self.graph.ci
        if show and self._placeholder is None:
            self._placeholder = pg.LabelItem(
                    "All graphs are detached: close their window to bring them back here",
                    color=theme.colors()["muted"])
            layout.addItem(self._placeholder, row=0, col=0)
        elif not show and self._placeholder is not None:
            layout.removeItem(self._placeholder)
            self._placeholder = None

    def _connect_scene(self, scene):
        """Souris dans la scène d'une fenêtre détachée : comme dans la fenêtre principale."""
        scene.sigMouseMoved.connect(lambda pos, s=scene: self._on_mouse_moved((pos,), s))
        scene.sigMouseClicked.connect(lambda ev, s=scene: self._remember_context_click(ev, s))
        scene.sigMouseClicked.connect(
                lambda ev, s=scene: self.range_picker._on_mouse_clicked(ev, s))

    # ---------------- hauteur des graphiques ----------------

    # hauteur minimale d'un graphique pendant le glisser d'une poignée (pixels)
    MIN_PANEL_HEIGHT = 60

    def heights(self) -> list[float]:
        """Hauteurs relatives des graphiques affichés (moyenne 1)."""
        values = self._heights[:len(self.panels)]
        values += [1.0] * (len(self.panels) - len(values))
        mean = sum(values) / len(values)
        return [round(v / mean, 3) for v in values]

    def set_heights(self, heights):
        """Hauteurs relatives souhaitées (projet relu ; [] : hauteurs égales)."""
        self._heights = [float(h) for h in (heights or []) if float(h) > 0]
        self._apply_heights()

    def reset_heights(self):
        """Même hauteur pour tous les graphiques (double-clic sur une poignée)."""
        self._heights = []
        self._apply_heights()
        self.heights_changed.emit(self.heights())

    def _apply_heights(self):
        """
        Hauteur préférée ET facteur d'étirement proportionnels à la hauteur souhaitée :
        la place disponible est répartie exactement selon ces proportions.
        """
        layout = self.graph.ci.layout
        ratios = dict(zip(self.panels, self.heights()))
        attached = self.attached_panels()
        if attached:
            mean = sum(ratios[panel] for panel in attached) / len(attached)
            for row, panel in enumerate(attached):
                ratio = ratios[panel] / mean
                panel.plot.setPreferredHeight(60 * ratio)
                layout.setRowStretchFactor(row, max(1, int(round(1000 * ratio))))
        layout.invalidate()

    def drag_splitter(self, index: int, scene_y: float):
        """
        Limite entre les graphiques index et index + 1 de la fenêtre principale amenée à
        l'ordonnée scene_y.
        """
        attached = self.attached_panels()
        rects = [panel.plot.sceneBoundingRect() for panel in attached]
        pixels = [rect.height() for rect in rects]
        pair = pixels[index] + pixels[index + 1]
        top = rects[index].top()
        minimum = min(self.MIN_PANEL_HEIGHT, pair / 2)
        pixels[index] = min(max(scene_y - top, minimum), pair - minimum)
        pixels[index + 1] = pair - pixels[index]
        # pixels convertis dans l'unité des hauteurs relatives (graphiques détachés
        # compris, qui gardent la leur)
        heights = self.heights() + self._heights[len(self.panels):]
        scale = sum(heights[self.panels.index(p)] for p in attached) / sum(
                    rect.height() for rect in rects)
        for panel, value in zip(attached, pixels):
            heights[self.panels.index(panel)] = value * scale
        self._heights = heights
        self._apply_heights()

    def _place_splitters(self):
        """Poignées entre les graphiques (après une modification de la mise en page)."""
        attached = self.attached_panels()
        for splitter in self._splitters:
            if splitter.index + 1 >= len(attached):
                # graphique détaché à l'instant : poignée retirée par _layout_panels
                continue
            upper = attached[splitter.index].plot.sceneBoundingRect()
            lower = attached[splitter.index + 1].plot.sceneBoundingRect()
            middle = (upper.bottom() + lower.top()) / 2
            height = PanelSplitter.HEIGHT
            splitter.place(QtCore.QRectF(upper.left(), middle - height / 2,
                                         upper.width(), height))

    # ---------------- numéro de graphique (paramètre « Graph ») ----------------

    @staticmethod
    def graph_number(obj) -> int:
        """Numéro du panneau d'une voie ou d'un texte (1 : panneau du haut)."""
        try:
            return max(1, int(getattr(obj, "graph_number", getattr(obj, "graph", 1)) or 1))
        except (TypeError, ValueError):
            return 1

    def panel_number(self, number: int) -> PlotPanel:
        """Panneau n° number (1 : celui du haut), créé avec ceux qui manquent."""
        while len(self.panels) < number:
            self.add_panel()
        return self.panels[number - 1]

    def plot_of(self, sig) -> pg.PlotItem:
        """Tracé du panneau d'un signal (celui de son paramètre « Graph »)."""
        panel = self.panel_of(sig)
        if panel is None:
            number = self.graph_number(sig)
            panel = self.panels[number - 1] if number <= len(self.panels) else self.main_panel
        return panel.plot

    def graph_number_at(self, scene_pos) -> int:
        """
        Graphique visé par un dépôt : celui sous le point (axes compris) ; sous le dernier
        graphique, un nouveau (dans la limite de MAX_GRAPHS).
        """
        attached = self.attached_panels()
        new_graph = min(len(self.panels) + 1, MAX_GRAPHS)
        if not attached:
            # tous les graphiques sont détachés : nouveau graphique
            return new_graph
        for panel in attached:
            if panel.plot.sceneBoundingRect().contains(scene_pos):
                return self.number_of_panel(panel)
        if scene_pos.y() > attached[-1].plot.sceneBoundingRect().bottom():
            return new_graph
        first = attached[0]
        return self.number_of_panel(
                first if scene_pos.y() < first.plot.sceneBoundingRect().top() else attached[-1])

    def show_drop_target(self, number: int | None):
        """Cadre sur le graphique visé pendant un glisser (None : retiré)."""
        scene = self.graph.scene()
        if self._drop_frame is None:
            color = QtGui.QColor(theme.colors()["accent"])
            self._drop_frame = QtWidgets.QGraphicsRectItem()
            self._drop_frame.setPen(pg.mkPen(color, width=2, style=QtCore.Qt.PenStyle.DashLine))
            color.setAlpha(30)
            self._drop_frame.setBrush(color)
            self._drop_frame.setZValue(1e6)
            scene.addItem(self._drop_frame)
        if number is None:
            self._drop_frame.hide()
            return
        attached = self.attached_panels()
        if number <= len(self.panels) and self.panels[number - 1] in attached:
            rect = self.panels[number - 1].plot.sceneBoundingRect()
        elif attached:
            # nouveau graphique : bande sous le dernier
            last = attached[-1].plot.sceneBoundingRect()
            rect = QtCore.QRectF(last.left(), last.bottom() - 30, last.width(), 30)
        else:
            rect = self.graph.ci.sceneBoundingRect()
        self._drop_frame.setRect(rect)
        self._drop_frame.show()

    def number_of_panel(self, panel) -> int:
        return self.panels.index(panel) + 1 if panel in self.panels else 1

    def trim_panels(self):
        """Panneaux du bas retirés quand plus aucune courbe ni aucun texte n'y est."""
        needed = max([1] + [self.graph_number(sig) for sig in self.curves]
                     + [self.graph_number(a) for a in self.graph_tree_ctrl.annotations()])
        while len(self.panels) > needed:
            self._remove_panel(self.panels[-1])

    def _move_curve(self, sig, panel):
        """Courbe de sig déplacée dans un autre panneau (paramètre « Graph » modifié)."""
        current = self.panel_of(sig)
        if current is panel or current is None:
            return
        current.remove_curve(sig)
        panel.add_curve(sig, self._on_curve_clicked)
        self._apply_curve_pen(sig, highlighted = sig is self.old_highlight)

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
        """Courbes de tous les panneaux : signal -> courbe (ordre des panneaux)."""
        if len(self.panels) == 1:
            return self.main_panel.curves
        return {sig: curve for panel in self.panels for sig, curve in panel.curves.items()}

    def panel_of(self, sig) -> PlotPanel | None:
        """Panneau où la courbe de sig est tracée."""
        return next((panel for panel in self.panels if sig in panel.curves), None)

    def panel_at(self, scene_pos, scene=None) -> PlotPanel | None:
        """
        Panneau sous un point de l'écran (coordonnées de la scène scene : par défaut celle
        de la fenêtre principale, sinon celle d'un graphique détaché).
        """
        scene = scene or self.graph.scene()
        return next((panel for panel in self.panels
                     if panel.plot.scene() is scene and panel.contains(scene_pos)), None)

    def _apply_theme(self):
        """Fond (option « Graph Background color » ou celui du thème), axes et textes."""
        dark = theme.is_dark(self.opts.get("dark_mode", False))
        background = theme.graph_background(self.opts["background_color"], dark)
        self.graph.setBackground(background)
        for panel in self.panels:
            panel.apply_theme(dark)
            if panel.window is not None:
                panel.window.view.setBackground(background)
        if self._placeholder is not None:
            self._placeholder.setText(self._placeholder.text, color=theme.colors(dark)["muted"])
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
        """Courbe de sig, dans panel (par défaut celui de son paramètre « Graph »)."""
        if self.panel_of(sig) is None:
            panel = panel or self.panel_number(self.graph_number(sig))
            panel.add_curve(sig, self._on_curve_clicked)

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
        # paramètre « Graph » modifié : la courbe (et ses signaux dérivés) change de panneau
        target = self.panel_number(self.graph_number(sig))
        if target is not panel:
            for moved in [sig] + list(getattr(sig, "derived_signals", [])):
                self._move_curve(moved, target)
            panel = target
            self.trim_panels()
            if sig is self.old_highlight:
                self._sync_active_panel()
        panel.redraw(sig)
        # la courbe sélectionnée reste mise en évidence
        self._apply_curve_pen(sig, highlighted = sig is self.old_highlight)
        panel.curves[sig].setVisible(sig.visible)
        # unité de la voie modifiée : la courbe change d'échelle
        panel.update_units()
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
        self._sync_active_panel()

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
            self.trim_panels()

    def _init_cursor(self):

        self.graph_tree_ctrl = GraphTreeController(self.plot,self.graph_tree,**self.opts)
        # textes : panneau de leur numéro de graphique (créé si besoin : projet relu)
        self.graph_tree_ctrl.plot_for_graph = lambda number: self.panel_number(number).plot
        self.graph_tree_ctrl.annotations_removed = self.trim_panels
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

    def _on_mouse_moved(self, ev, scene=None):
        # Garde 2: souris sur le viewbox ?
        pos = ev[0]
        panel = self.panel_at(pos, scene)
        if panel is not None:

            mousePoint = panel.vb.mapSceneToView(pos)
            # Y conservé pour le curseur libre (non accroché à une courbe)
            self._mouse_pos = mousePoint
            self._mouse_panel = panel
            self.cursor_moved_X.emit(float(mousePoint.x()))

    #MAJ de la position du curseur grâce à la position de la souris
    def _update_cursor(self, x: float, y: float | None):

        if x is None:
            return
        cursor = self.graph_tree_ctrl.mouseCursor
        if y is None:
            # curseur libre : il suit la souris, dans le panneau survolé
            y = float(self._mouse_pos.y())
            panel = getattr(self, "_mouse_panel", None) or self.main_panel
            cursor.set_graph(panel.plot)
            cursor.mouseUpdate(x, y)
            return
        # curseur accroché à la courbe sélectionnée : son panneau et son échelle
        sig = self.old_highlight
        panel = self.panel_of(sig) if sig is not None else None
        panel = panel or self.main_panel
        cursor.set_graph(panel.plot)
        cursor.mouseUpdate(x, y, y_view=panel.to_main_y(sig, y) if sig is not None else None)

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

    def _remember_context_click(self, ev, scene=None):
        """Mémorise la position du clic droit (ouverture du menu contextuel)."""
        if (ev.button() == QtCore.Qt.MouseButton.RightButton and
                self.panel_at(ev.scenePos(), scene) is not None):
            self._context_scene_pos = QtCore.QPointF(ev.scenePos())
            self._context_scene = scene

    def nearest_sample(self, sig, scene_pos: QtCore.QPointF) -> tuple[float, float] | None:
        """Échantillon de sig le plus proche d'un point de l'écran (PlotPanel.nearest_sample)."""
        return (self.panel_of(sig) or self.main_panel).nearest_sample(sig, scene_pos)

    def add_text_annotation(self, scene_pos: QtCore.QPointF | None = None, scene=None):
        """
        Ajoute un texte à la position du clic droit (scene_pos par défaut). Si une courbe
        visible est sélectionnée, le texte annote son échantillon le plus proche du clic :
        il est relié par une flèche et prérempli avec la valeur de l'échantillon.
        """
        if scene_pos is None:
            scene_pos, scene = self._context_scene_pos, self._context_scene
        if scene_pos is None:
            scene_pos = self.main_panel.vb.sceneBoundingRect().center()
            scene = self.main_panel.plot.scene()
        # texte placé dans le panneau du clic (fenêtre principale ou graphique détaché)
        panel = self.panel_at(scene_pos, scene) or self.main_panel
        vb = panel.vb
        graph = self.number_of_panel(panel)

        sig = self.old_highlight
        sample = None
        # échantillon annoté : courbe sélectionnée du même panneau
        if (sig is not None and sig in panel.curves and panel.curves[sig].isVisible()):
            sample = self.nearest_sample(sig, scene_pos)

        if sample is None:
            click = vb.mapSceneToView(scene_pos)
            return self.graph_tree_ctrl.addText(pos=(click.x(), click.y()), graph=graph)

        x, y = sample
        # flèche et texte placés dans les coordonnées de l'échelle principale du panneau
        y_view = panel.to_main_y(sig, y)
        text_scene = vb.mapViewToScene(QtCore.QPointF(x, y_view)) + self.ANNOTATION_OFFSET
        text_pos = vb.mapSceneToView(text_scene)
        unit = getattr(sig, 'unit', '') or ''
        text = f"{sig.name}\n{y:.2f} {unit} @ {x:.0f} {self.opts['X_unit']}"
        return self.graph_tree_ctrl.addText(pos         = (text_pos.x(), text_pos.y()),
                                            anchor_pos  = (x, y_view),
                                            text        = text,
                                            color       = sig.pen.color(),
                                            graph       = graph)

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