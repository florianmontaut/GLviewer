# tests/test_mouse_cursor.py
"""Curseur souris (outils graphiques) : accroche à la courbe sélectionnée et couleur."""
import pytest
from PyQt6 import QtCore, QtGui

from ressources.custom_items import SelectionContext
from helpers import load

GREY = QtGui.QColor(100, 100, 100)


@pytest.fixture
def graph(ctrl, csv_files, qapp):
    load(ctrl, csv_files[0])
    ctrl.view.resize(1200, 800)
    ctrl.view.show()
    qapp.processEvents()
    vb = ctrl.graph_ctrl.vb
    vb.disableAutoRange()
    vb.setRange(xRange=(0, 600), yRange=(15, 50), padding=0)
    qapp.processEvents()
    return ctrl.graph_ctrl


def _cursor(graph):
    return graph.graph_tree_ctrl.mouseCursor


def _show(graph, snap):
    cursor = _cursor(graph)
    cursor.param('show cursors').setValue(True)
    cursor.param('snap to selected signal').setValue(snap)


def _move_mouse(graph, qapp, x, y):
    """Mouvement de souris au point (x, y) des données (SignalProxy : 50 Hz)."""
    scene_pos = graph.vb.mapViewToScene(QtCore.QPointF(x, y))
    graph._on_mouse_moved((scene_pos,))
    qapp.processEvents()


def _select_in_tree(ctrl, sig):
    ctrl.view.treefile.setCurrentIndex(ctrl.model.signal_index(sig))


def _lines(graph):
    vertical, horizontal = _cursor(graph).cursors
    return vertical.value(), horizontal.value()


def test_free_cursor_follows_mouse(ctrl, graph, qapp):
    _show(graph, snap=False)
    _move_mouse(graph, qapp, 300, 33)
    x, y = _lines(graph)
    assert x == pytest.approx(300, abs=0.5) and y == pytest.approx(33, abs=0.1)


def test_snapped_cursor_follows_selected_curve(ctrl, graph, qapp):
    sig = ctrl.workspace.files[0].signals[0]
    _show(graph, snap=True)
    _select_in_tree(ctrl, sig)

    _move_mouse(graph, qapp, 300, 18)                 # souris loin de la courbe en Y
    x, y = _lines(graph)
    assert x == pytest.approx(300, abs=0.5)
    assert y == pytest.approx(sig.nearest_value(x))


def test_snap_follows_selection_change(ctrl, graph, qapp):
    ch1, ch2 = ctrl.workspace.files[0].signals
    _show(graph, snap=True)
    _select_in_tree(ctrl, ch1)
    _move_mouse(graph, qapp, 300, 18)
    _select_in_tree(ctrl, ch2)
    _move_mouse(graph, qapp, 300, 18)
    assert _lines(graph)[1] == pytest.approx(ch2.nearest_value(_lines(graph)[0]))


def test_snap_from_curve_click(ctrl, graph, qapp):
    sig = ctrl.workspace.files[0].signals[1]
    _show(graph, snap=True)
    graph._on_curve_clicked(graph.curves[sig], None)
    _move_mouse(graph, qapp, 200, 40)
    assert _lines(graph)[1] == pytest.approx(sig.nearest_value(_lines(graph)[0]))


def test_unchecking_snap_frees_cursor(ctrl, graph, qapp):
    _show(graph, snap=True)
    _select_in_tree(ctrl, ctrl.workspace.files[0].signals[0])
    _cursor(graph).param('snap to selected signal').setValue(False)
    _move_mouse(graph, qapp, 300, 33)
    assert _lines(graph)[1] == pytest.approx(33, abs=0.1)


def test_file_selection_frees_cursor(ctrl, graph, qapp):
    _show(graph, snap=True)
    _select_in_tree(ctrl, ctrl.workspace.files[0].signals[0])
    file_item = ctrl.model.find_item(ctrl.model.root, ctrl.workspace.files[0])
    ctrl.view.treefile.setCurrentIndex(ctrl.model.index_from_item(file_item))
    _move_mouse(graph, qapp, 300, 33)
    assert _lines(graph)[1] == pytest.approx(33, abs=0.1)


def test_cursor_takes_selected_curve_color(ctrl, graph):
    sig = ctrl.workspace.files[0].signals[0]
    _show(graph, snap=True)
    _select_in_tree(ctrl, sig)

    for line in _cursor(graph).cursors:
        assert line.pen.color() == sig.pen.color()

    _cursor(graph).param('snap to selected signal').setValue(False)
    for line in _cursor(graph).cursors:
        assert line.pen.color() == GREY


def test_value_text_follows_snapped_point(ctrl, graph, qapp):
    sig = ctrl.workspace.files[0].signals[0]
    _show(graph, snap=True)
    _cursor(graph).param('show Y value').setValue(True)
    _select_in_tree(ctrl, sig)
    _move_mouse(graph, qapp, 300, 18)

    text = _cursor(graph).valtext
    assert text.parentItem() is not None and text.pos().x() == pytest.approx(_lines(graph)[0])
    assert f"{sig.nearest_value(_lines(graph)[0]):0.1f}" in text.toPlainText()
