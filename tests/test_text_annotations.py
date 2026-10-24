# tests/test_text_annotations.py
"""Texte ajouté par le menu contextuel du graphique, et annotation d'une courbe."""
import numpy as np
import pytest
from PyQt6 import QtCore, QtGui

from ressources.custom_types import qSignalType as T
from ressources.custom_items import SelectionContext
from ressources.custom_dialogs import pgText
from helpers import load


@pytest.fixture
def graph(ctrl, csv_files, qapp):
    """Fenêtre affichée (hors écran) avec une vue fixe : x ∈ [0, 600], y ∈ [15, 50]."""
    load(ctrl, csv_files[0])
    ctrl.view.resize(1200, 800)
    ctrl.view.show()
    qapp.processEvents()
    vb = ctrl.graph_ctrl.vb
    vb.disableAutoRange()
    vb.setRange(xRange=(0, 600), yRange=(15, 50), padding=0)
    qapp.processEvents()
    return ctrl.graph_ctrl


class RightClick:
    """Clic droit simulé dans le graphique, à la position (x, y) des données."""
    def __init__(self, graph, x, y, button=QtCore.Qt.MouseButton.RightButton):
        self._pos = graph.vb.mapViewToScene(QtCore.QPointF(x, y))
        self._button = button
    def button(self): return self._button
    def scenePos(self): return self._pos


def _right_click(graph, x, y):
    graph._remember_context_click(RightClick(graph, x, y))


def _texts(graph):
    return [i for i in graph.plot.items if isinstance(i, pgText)]


def _select(ctrl, sig):
    ctrl.graph_ctrl.select_graph_from_context(SelectionContext(role=sig.item_type, signal=sig))


def _scene(graph, point):
    return graph.vb.mapViewToScene(QtCore.QPointF(*point))


# ---------------- texte libre ----------------

def test_text_appears_at_right_click_position(ctrl, graph):
    _right_click(graph, 150, 30)

    graph.actions_forwarding(T.TEXT)

    text = _texts(graph)[0]
    assert (text.pos().x(), text.pos().y()) == pytest.approx((150, 30), abs=0.5)
    assert text.lineItem is None and text.arrow is None
    assert text.window is not None and text.window.isVisible()   # éditeur ouvert
    text.window.reject()


def test_cancelled_empty_text_is_removed(ctrl, graph):
    _right_click(graph, 150, 30)
    graph.actions_forwarding(T.TEXT)
    text = _texts(graph)[0]

    text.window.reject()

    assert _texts(graph) == [] and graph.graph_tree_ctrl.textItems == {}


def test_accepted_text_is_kept(ctrl, graph):
    _right_click(graph, 150, 30)
    graph.actions_forwarding(T.TEXT)
    text = _texts(graph)[0]

    text.window.textEdit.setText("Début de l'essai")
    text.window.accept()

    assert text.toPlainText() == "Début de l'essai"
    assert _texts(graph) == [text]


def test_left_click_does_not_move_text_position(ctrl, graph):
    _right_click(graph, 150, 30)
    graph._remember_context_click(RightClick(graph, 500, 20,
                                             button=QtCore.Qt.MouseButton.LeftButton))
    graph.add_text_annotation().window.reject()
    graph.actions_forwarding(T.TEXT)
    text = _texts(graph)[0]
    assert text.pos().x() == pytest.approx(150, abs=0.5)
    text.window.reject()


# ---------------- annotation d'une courbe sélectionnée ----------------

def test_nearest_sample_uses_screen_distance(ctrl, graph):
    sig = ctrl.workspace.files[0].signals[0]
    click = _scene(graph, (300, 25))

    x, y = graph.nearest_sample(sig, click)

    # référence : recherche exhaustive en pixels
    distances = [QtCore.QLineF(_scene(graph, (xi, yi)), click).length()
                 for xi, yi in zip(sig.x, sig.y)]
    i = int(np.argmin(distances))
    assert (x, y) == (pytest.approx(sig.x[i]), pytest.approx(sig.y[i]))


def test_selected_curve_annotation(ctrl, graph):
    sig = ctrl.workspace.files[0].signals[0]
    _select(ctrl, sig)
    _right_click(graph, 300, 25)

    graph.actions_forwarding(T.TEXT)

    text = _texts(graph)[0]
    x, y = graph.nearest_sample(sig, _scene(graph, (300, 25)))
    assert text.anchor_pos == pytest.approx((x, y))
    assert sig.name in text.toPlainText() and f"{y:.2f}" in text.toPlainText()
    assert text.color == sig.pen.color()
    # texte au-dessus à droite du point annoté (à l'écran)
    text_scene, anchor_scene = text.mapToScene(text.boundingRect().bottomLeft()), _scene(graph, (x, y))
    assert text_scene.x() > anchor_scene.x() and text_scene.y() < anchor_scene.y()
    text.window.reject()                       # texte prérempli : conservé
    assert _texts(graph) == [text]


def _check_arrow(graph, text):
    """La ligne relie le coin du texte le plus proche au point annoté, la pointe y est."""
    anchor = QtCore.QPointF(*text.anchor_pos)
    line = text.lineItem.line()
    assert line.p2() == anchor
    assert text.arrow.pos() == anchor
    start_scene = graph.vb.mapViewToScene(line.p1())
    corners = [text.mapToScene(c) for c in (text.boundingRect().topLeft(),
                                            text.boundingRect().topRight(),
                                            text.boundingRect().bottomLeft(),
                                            text.boundingRect().bottomRight())]
    anchor_scene = graph.vb.mapViewToScene(anchor)
    closest = min(corners, key=lambda c: QtCore.QLineF(c, anchor_scene).length())
    assert QtCore.QLineF(start_scene, closest).length() < 1.0
    # la pointe (point (0,0) du dessin) est sur le point annoté et la flèche est orientée
    # vers lui : le reste du dessin (sa base) est du côté du texte. Mesure à l'écran :
    # la flèche ignore les transformations (taille en pixels), mapToScene ne convient pas
    viewport = graph.graph.viewportTransform()
    device = text.arrow.deviceTransform(viewport)
    tip = device.map(QtCore.QPointF(0, 0))
    # milieu des deux sommets de la base de la tête (sur l'axe de la flèche, cf.
    # pyqtgraph.functions.makeArrowPath : moveTo(0,0), base haute, creux, base basse...)
    path = text.arrow.path
    base_1, base_2 = path.elementAt(1), path.elementAt(3)
    tail = device.map(QtCore.QPointF((base_1.x + base_2.x) / 2, (base_1.y + base_2.y) / 2))
    anchor_px, start_px = viewport.map(anchor_scene), viewport.map(start_scene)
    assert QtCore.QLineF(tip, anchor_px).length() < 1.0
    towards_text = QtCore.QPointF(start_px - anchor_px)
    tail_dir = QtCore.QPointF(tail - tip)
    cos = ((towards_text.x()*tail_dir.x() + towards_text.y()*tail_dir.y()) /
           (QtCore.QLineF(QtCore.QPointF(), towards_text).length() *
            QtCore.QLineF(QtCore.QPointF(), tail_dir).length()))
    assert cos > 0.99       # flèche alignée sur la ligne texte -> point annoté


def _annotate(ctrl, graph, x=300, y=25):
    sig = ctrl.workspace.files[0].signals[0]
    _select(ctrl, sig)
    _right_click(graph, x, y)
    text = graph.add_text_annotation()
    text.window.reject()
    return text


def test_arrow_geometry(ctrl, graph):
    _check_arrow(graph, _annotate(ctrl, graph))


@pytest.mark.parametrize("move", [(-200, 0), (0, -15), (150, 10)])
def test_arrow_follows_moved_text(ctrl, graph, move):
    text = _annotate(ctrl, graph)
    text.setPos(text.pos() + QtCore.QPointF(*move))
    _check_arrow(graph, text)


def test_arrow_follows_moved_anchor(ctrl, graph):
    text = _annotate(ctrl, graph)
    text.anchorHandle.setPos(QtCore.QPointF(100, 40))

    assert text.anchor_pos == pytest.approx((100, 40))
    _check_arrow(graph, text)


def test_arrow_follows_zoom(ctrl, graph, qapp):
    text = _annotate(ctrl, graph)
    graph.vb.setRange(xRange=(250, 400), yRange=(20, 45), padding=0)
    qapp.processEvents()
    _check_arrow(graph, text)


def test_delete_key_removes_annotation(ctrl, graph):
    text = _annotate(ctrl, graph)
    parts = (text, text.lineItem, text.arrow, text.anchorHandle)

    text.keyPressEvent(QtGui.QKeyEvent(QtCore.QEvent.Type.KeyPress,
                                       QtCore.Qt.Key.Key_Delete,
                                       QtCore.Qt.KeyboardModifier.NoModifier))

    assert not any(part in graph.plot.items for part in parts)
    assert graph.graph_tree_ctrl.textItems == {}
    graph.vb.setRange(xRange=(0, 100), padding=0)   # plus de mise à jour de la flèche


def test_hidden_selected_curve_gives_plain_text(ctrl, graph):
    sig = ctrl.workspace.files[0].signals[0]
    _select(ctrl, sig)
    graph.curves[sig].setVisible(False)
    _right_click(graph, 300, 25)

    text = graph.add_text_annotation()

    assert text.anchor_pos is None and text.lineItem is None
    text.window.reject()
