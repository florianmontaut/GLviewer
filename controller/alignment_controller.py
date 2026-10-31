# controller/alignment_controller.py
"""
Recalage d'un enregistrement dans le temps (« Align in time… ») : un fichier lancé avant
ou après les autres (ex: NTC démarrées 25 min après le Graphtec) est décalé à vue, sur
des événements communs (chute du débit d'eau -> montée des NTC des IGBT).

Pendant le recalage, les courbes du fichier suivent l'écart en direct, simplifiées
(min / max par paquets) sur les gros enregistrements ; les autres sont estompées et rien
n'est recalculé. L'écart est validé en une seule fois : décalage du
fichier (une entrée de l'historique), analyses et voies calculées recalculées.

    - poignée ⇔ : glisser pour décaler les courbes du fichier
    - panneau : écart saisi (s), pas de ±1 s / ±10 s / ±1 min
    - points A (événement du fichier) et B (même événement sur une référence) :
      « Aligner A sur B » ajoute l'écart B - A
"""
import warnings

import numpy as np
import pyqtgraph as pg
from PyQt6 import QtCore, QtGui, QtWidgets

FADED_OPACITY = 0.25
# courbes simplifiées pendant le recalage : au plus ~2 x PREVIEW_BLOCKS points par courbe
PREVIEW_BLOCKS = 10_000


def simplified(x, y, blocks: int = PREVIEW_BLOCKS):
    """
    Courbe simplifiée pour le recalage : min et max de chaque paquet de points (les pics,
    ex: montée des NTC, restent visibles). Courbe inchangée si elle est assez petite.
    """
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    size = len(x) // blocks
    if size < 2:
        return x, y
    n = size * blocks
    yb = y[:n].reshape(blocks, size)
    xb = x[:n].reshape(blocks, size)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)      # paquet entièrement manquant
        lo, hi = np.nanmin(yb, axis=1), np.nanmax(yb, axis=1)
    xs = np.column_stack((xb[:, 0], xb[:, -1])).ravel()
    ys = np.column_stack((lo, hi)).ravel()
    return np.append(xs, x[n:]), np.append(ys, y[n:])


def format_duration(seconds: float) -> str:
    """Écart lisible : « +27 min 14.0 s », « -1 h 02 min 05.0 s », « +0.250 s »."""
    sign = "-" if seconds < 0 else "+"
    s = abs(seconds)
    if s < 60:
        return f"{sign}{s:.3f} s"
    hours, rest = divmod(s, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{sign}{int(hours)} h {int(minutes):02d} min {secs:04.1f} s"
    return f"{sign}{int(minutes)} min {secs:04.1f} s"


class AlignmentPanel(QtWidgets.QFrame):
    """Barre du recalage (barre d'état de la fenêtre principale)."""

    STEPS = ((-60, "-1 min"), (-10, "-10 s"), (-1, "-1 s"), (1, "+1 s"), (10, "+10 s"),
             (60, "+1 min"))

    def __init__(self, file_name: str, parent=None):
        super().__init__(parent)
        self.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 6, 0)
        layout.addWidget(QtWidgets.QLabel(f"Recalage de « {file_name} » — écart :"))
        self.offset = QtWidgets.QDoubleSpinBox()
        self.offset.setRange(-1e8, 1e8)
        self.offset.setDecimals(3)
        self.offset.setSuffix(" s")
        self.offset.setKeyboardTracking(False)
        layout.addWidget(self.offset)
        self.readable = QtWidgets.QLabel()
        self.readable.setMinimumWidth(130)
        layout.addWidget(self.readable)
        self.step_buttons = {}
        for step, text in self.STEPS:
            button = QtWidgets.QToolButton(text=text)
            layout.addWidget(button)
            self.step_buttons[step] = button
        self.align_button = QtWidgets.QPushButton("Aligner A sur B")
        self.align_button.setToolTip("Place l'événement A du fichier sur l'événement B "
                                     "de la référence (lignes A et B du graphique)")
        self.validate_button = QtWidgets.QPushButton("Valider")
        self.cancel_button = QtWidgets.QPushButton("Annuler")
        for button in (self.align_button, self.validate_button, self.cancel_button):
            layout.addWidget(button)


class AlignmentController(QtCore.QObject):

    # validation : (fichier, écart à ajouter à son décalage, en s)
    accepted = QtCore.pyqtSignal(object, float)
    cancelled = QtCore.pyqtSignal(object)

    HINT = ("Recalage : glissez la poignée ⇔ (ou saisissez l'écart), ou placez A sur un "
            "événement du fichier et B sur le même événement d'une référence puis "
            "« Aligner A sur B ». Entrée : valider, Échap : annuler.")

    def __init__(self, graph_ctrl, window: QtWidgets.QMainWindow):
        super().__init__()
        self.graph = graph_ctrl
        self.window = window
        self.file = None
        self.delta = 0.0
        self.panel = None
        self._items = []
        self._shortcuts = []
        # courbes redessinées au plus toutes les 30 ms pendant un glissement
        self._redraw_timer = QtCore.QTimer(self)
        self._redraw_timer.setSingleShot(True)
        self._redraw_timer.setInterval(30)
        self._redraw_timer.timeout.connect(self._redraw)

    @property
    def active(self) -> bool:
        return self.file is not None

    # ---------------- début / fin ----------------

    def start(self, file_obj):
        if self.active:
            self.cancel()
        self.file = file_obj
        self.delta = 0.0
        self._a = None                       # instant A en temps du fichier (avant écart)
        (x0, x1), _ = self.graph.vb.viewRange()
        span = x1 - x0
        self._preview = {}
        for sig, curve in self.graph.curves.items():
            if not self._moves(sig):
                curve.setOpacity(FADED_OPACITY)
            else:
                self._preview[sig] = simplified(sig.x, self.graph._display_y(sig))

        pen = pg.mkPen((230, 120, 0), width=2, style=QtCore.Qt.PenStyle.DashLine)
        self.handle = pg.InfiniteLine(pos=x0 + span / 2, movable=True, pen=pen,
                                      label="⇔ décaler", labelOpts={"position": 0.95,
                                      "color": (230, 120, 0), "movable": False})
        self._handle_origin = self.handle.value()
        self.handle.sigPositionChanged.connect(self._on_handle_moved)
        self.point_a = pg.InfiniteLine(pos=x0 + span / 3, movable=True,
                                       pen=pg.mkPen((0, 150, 220), width=2),
                                       label="A : fichier", labelOpts={"position": 0.85,
                                       "color": (0, 150, 220)})
        self._a = self.point_a.value()
        self.point_a.sigPositionChanged.connect(self._on_a_moved)
        self.point_b = pg.InfiniteLine(pos=x0 + 2 * span / 3, movable=True,
                                       pen=pg.mkPen((40, 170, 60), width=2),
                                       label="B : référence", labelOpts={"position": 0.85,
                                       "color": (40, 170, 60)})
        self._items = [self.handle, self.point_a, self.point_b]
        for item in self._items:
            self.graph.plot.addItem(item, ignoreBounds=True)

        self.panel = AlignmentPanel(file_obj.label or file_obj.name)
        self.panel.offset.valueChanged.connect(self.set_delta)
        for step, button in self.panel.step_buttons.items():
            button.clicked.connect(lambda _=False, s=step: self.set_delta(self.delta + s))
        self.panel.align_button.clicked.connect(self.align_points)
        self.panel.validate_button.clicked.connect(self.validate)
        self.panel.cancel_button.clicked.connect(self.cancel)
        self.window.statusBar().addPermanentWidget(self.panel)
        self.window.statusBar().showMessage(self.HINT)
        for key, slot in ((QtCore.Qt.Key.Key_Return, self.validate),
                          (QtCore.Qt.Key.Key_Enter, self.validate),
                          (QtCore.Qt.Key.Key_Escape, self.cancel)):
            shortcut = QtGui.QShortcut(QtGui.QKeySequence(key), self.window)
            shortcut.setContext(QtCore.Qt.ShortcutContext.WindowShortcut)
            shortcut.activated.connect(slot)
            self._shortcuts.append(shortcut)
        self._show_delta()

    def validate(self):
        if not self.active:
            return
        file_obj, delta = self.file, self.delta
        self._finish()
        self.accepted.emit(file_obj, delta)

    def cancel(self):
        if not self.active:
            return
        file_obj = self.file
        self._finish()
        for sig in list(self.graph.curves):
            if getattr(sig, "file", None) is file_obj:
                self.graph.update_signal(sig)     # courbes remises à leur place
        self.cancelled.emit(file_obj)

    def _finish(self):
        self._redraw_timer.stop()
        self._preview = {}
        for item in self._items:
            self.graph.plot.removeItem(item)
        self._items = []
        for curve in self.graph.curves.values():
            curve.setOpacity(1.0)
        for shortcut in self._shortcuts:
            shortcut.setEnabled(False)
            shortcut.deleteLater()
        self._shortcuts = []
        if self.panel is not None:
            self.window.statusBar().removeWidget(self.panel)
            self.panel.deleteLater()
            self.panel = None
        self.window.statusBar().clearMessage()
        self.file = None

    # ---------------- écart ----------------

    def _moves(self, sig) -> bool:
        """Courbe du fichier recalé (voies, voies calculées, courbes des analyses)."""
        return getattr(sig, "file", None) is self.file

    def set_delta(self, delta: float):
        if not self.active:
            return
        self.delta = float(delta)
        self._show_delta()
        self._redraw_timer.start()

    def _show_delta(self):
        with QtCore.QSignalBlocker(self.panel.offset):
            self.panel.offset.setValue(self.delta)
        self.panel.readable.setText(format_duration(self.delta))
        with QtCore.QSignalBlocker(self.handle):
            self.handle.setValue(self._handle_origin + self.delta)
        with QtCore.QSignalBlocker(self.point_a):
            self.point_a.setValue(self._a + self.delta)     # A reste sur son événement

    def _on_handle_moved(self, line):
        self.set_delta(line.value() - self._handle_origin)

    def _on_a_moved(self, line):
        self._a = line.value() - self.delta

    def align_points(self):
        """A (événement du fichier) placé sur B (même événement de la référence)."""
        self.set_delta(self.delta + self.point_b.value() - self.point_a.value())

    def _redraw(self):
        if not self.active:
            return
        for sig, (x, y) in self._preview.items():
            curve = self.graph.curves.get(sig)
            if curve is not None:
                curve.setData(x + self.delta, y)
