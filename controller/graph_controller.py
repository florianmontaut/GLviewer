
# controller/graph_controller.py

from PyQt6 import QtCore,QtGui,QtWidgets
import pyqtgraph as pg
import pyqtgraph.parametertree as ptree
from model.base_objects import SignalObject,DerivedSignalObject,SelectionContext
from ressources.custom_menu import SelectionState
from ressources import custom_graph_functions,custom_types,custom_items

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


class GraphController(QtCore.QObject):
    """
    Gère l'affichage PyQtGraph :
    - création courbes
    - update visibilité
    - update style
    - update pipeline (sig.y recalcule automatiquement)
    """

    curve_selected          = QtCore.pyqtSignal(SelectionContext)
    reference_requested     = QtCore.pyqtSignal(SignalObject)
    cursor_moved_X          = QtCore.pyqtSignal(float)
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
        self.old_highlight_width    = 1
        self.reference_sig          = None
        self.macro_recording        = False
        self.vcursor                = None
        self.xp_axis                = None
        self.yp_axis                = None
        self._mouse_pos             = 0

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
        "dark_mode"            : False
        }


        if opts:
            self.updateOptions(**opts)
        self._init_graph()
        self._init_graph_menu()
        self._init_cursor()

    @property
    def mouse_pos(self):
        return self._mouse_pos #x = float(mouse_point.x())


    #! à revoir, en l'état si le fichier .JSON n'est pas conforme, ça peut planter le graph_ctrl
    #! peut-être faire une validation plus poussée dans le menu_controller avant d'appeler updateOptions
    def updateOptions(self,opts=None):
        if opts is not None:
            self.opts.update(opts)

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
        self.graph_tree_ctrl.update_settings(opts)


    def _init_graph(self):

        self.plot = pg.PlotItem(None,axisItems={"bottom": self.time_axis})
        self.graph.addItem(self.plot)
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

    def update_vbox(self):
        self.vb.autoRange()

    # ----------------------------------------------------
    def add_signal_curve(self, sig: SignalObject|DerivedSignalObject):

        if sig not in self.curves.keys():
            curve = pg.PlotDataItem(sig.x, sig.y, pen=sig.pen)
            curve.setCurveClickable(True)
            curve.sigClicked.connect(self._on_curve_clicked)
            self.plot.addItem(curve)
            self.curves[sig] = curve

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
            ctx = SelectionContext(
                                    role=custom_items.itemType.DERIVED,
                                    signal=sig.parent_signal,
                                    derived_index=sig.parent_signal.derived_signals.index(sig),
                                    item=None,  # pas de TreeItem ici
                                )

        elif isinstance(sig, SignalObject):
            ctx = SelectionContext(
                                    role=custom_items.itemType.RAW,
                                    signal=sig,
                                    item=None,
                                )
        else:
            #print(f'failed: {sig} / {type(sig)}')
            return  # sécurité
        try:
            print(  "Graph_controller ligne 193: _on_curve_clicked => méthode appelée en cliquant sur une courbe: \n"+
                f'Signal: {ctx.signal.display_name}, role: {ctx.role}, filter index: {ctx.filter_index}'+
                f', Analysis index: {ctx.analysis_index}, derived index: {ctx.derived_index}\n')
        except:
            print('failed : échec d\'impression de données du CTX (Graph_controller)\n')
        self.curve_selected.emit(ctx)

    # ----------------------------------------------------
    def update_signal(self, sig):
        """Redessine la courbe après pipeline update."""
        if sig not in self.curves:
            return
        curve = self.curves[sig]
        curve.setData(sig.x, sig.y)
        curve.setPen(sig.pen)
        curve.setVisible(sig.visible)
        self.update_vbox()

    def freeze_updates(self, freeze: bool):
        self.graph.setUpdatesEnabled(not freeze)
        self.vb.enableAutoRange(False)
        if not freeze:
            self.update_vbox()
            self.vb.enableAutoRange(True)
            self.vb.autoRange()

    def select_graph_from_context(self,ctx:SelectionContext):

        self.highlight(ctx.signal)

    def highlight(self, sig):
        """Met en surbrillance le signal sélectionné."""

        curve = self.curves[sig]
        self._update_cursor_color(curve)
        self.on_selection_changed(sig)

        if self.old_highlight != sig:
            # Highlight the new signal: double its current width (which should match sig.pen.width() if not previously highlighted)
            double_width = int(curve.opts['pen'].width() * 2)
            custom_graph_functions.updateCurve(curve, width=double_width, z_val=10)

            # Deselect the old signal
            if self.old_highlight is not None:
                old_curve = self.curves[self.old_highlight]
                current_width = old_curve.opts['pen'].width()
                expected_doubled_width = 2 * self.old_highlight_width

                if current_width == expected_doubled_width:
                    # The width was doubled and not changed by the user; revert to original
                    custom_graph_functions.updateCurve(old_curve, width=self.old_highlight_width)
                else:
                    # The width was changed by the user (e.g., via parameter tree); keep the new width but reset highlight properties
                    # Assuming custom_graph_functions.updateCurve can update z_val without changing width if width is not provided
                    custom_graph_functions.updateCurve(old_curve, z_val=0)  # Replace 0 with the default z-value if known

            # Update tracking variables
            self.old_highlight = sig
            self.old_highlight_width = sig.pen.width()  # Store the original width for the new highlight

    def remove_signal_curve(self, signal):
        curve = self.curves.pop(signal, None)
        if curve is not None:

            self.plot.removeItem(curve)
            curve.setParentItem(None)
            curve.deleteLater()
            #self.plot.removeItem(curve) #crash intempestif lors des undo/redo

    def _init_cursor(self):

        self.graph_tree_ctrl=GraphTreeController(self.plot,self.graph_tree,**self.opts)
        self.proxy = pg.SignalProxy(self.plot.scene().sigMouseMoved,rateLimit = 50,
                                    slot = self._on_mouse_moved)


    def _update_cursor_color(self,curve):

        #self.graph_tree_ctrl.mouseCursor.setCurve(curve)
        pass


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
            self.cursor_moved_X.emit(float(mousePoint.x()))

    #MAJ de la position du curseur grâce à la position de la souris
    def _update_cursor(self, x: float, y: float | None):

        if x is None:
            return
        else:
            self.graph_tree_ctrl.mouseCursor.mouseUpdate(x,y,)

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
            self.graph_tree_ctrl.addText()
        else:
            self.menu_actions_triggered.emit(   custom_types.ActionModifier.ADD_ACTION,
                                                action_type,
                                                macro_name)

    def on_selection_changed(self,sig:SignalObject=None):

        # actuellement seul un signal d'un même DataFrame peut servir de référence.
        if sig is not None:
            states = SelectionState(
                                        has_selection = True,
                                        has_reference = (self.reference_sig is not None and
                                                        not sig.is_reference) ,
                                        is_recording= self.macro_recording
                                        )
        else:
            states = SelectionState(
                                        has_selection = False,
                                        has_reference = False,
                                        is_recording= self.macro_recording
                                        )

        self.menu.update_enabled_states(states)


    def set_reference_signal(self, sig : SignalObject):

        self.reference_sig = sig