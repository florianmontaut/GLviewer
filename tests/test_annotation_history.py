# tests/test_annotation_history.py
"""Textes du graphique : undo/redo (Ctrl+Z / Ctrl+Y) et sauvegarde dans le projet."""
import json

import pytest
from PyQt6 import QtCore, QtGui
from PyQt6.QtTest import QTest

from ressources.custom_dialogs import pgText
from model.annotations import TextAnnotation
from test_text_annotations import graph, RightClick, _right_click, _texts, _select  # noqa: F401


def _stack(ctrl):
    return ctrl.workspace_ctrl.undo_stack


def _annotations(ctrl):
    return list(ctrl.workspace.annotations.values())


def _free_text(ctrl, graph, x=150, y=30, content="Début de l'essai"):
    _right_click(graph, x, y)
    item = graph.add_text_annotation()
    item.window.textEdit.setText(content)
    item.window.accept()
    return item


def _curve_annotation(ctrl, graph, x=300, y=25):
    _select(ctrl, ctrl.workspace.files[0].signals[0])
    _right_click(graph, x, y)
    item = graph.add_text_annotation()
    item.window.reject()                    # texte prérempli conservé
    return item


def _arrow_parts(item):
    return (item.lineItem, item.arrow, item.anchorHandle)


def _item(ctrl, annotation_id):
    return ctrl.graph_ctrl.graph_tree_ctrl.textItems.get(annotation_id)


# ---------------- création ----------------

def test_created_text_is_one_undo_step(ctrl, graph):
    count = _stack(ctrl).count()
    item = _free_text(ctrl, graph)

    assert _stack(ctrl).count() == count + 1
    [annotation] = _annotations(ctrl)
    assert "Début de l'essai" in annotation.html
    assert annotation.pos == pytest.approx((150, 30), abs=0.5)
    assert annotation.anchor_pos is None

    _stack(ctrl).undo()
    assert _annotations(ctrl) == [] and _texts(graph) == []

    _stack(ctrl).redo()
    [restored] = _texts(graph)
    assert restored.toPlainText() == "Début de l'essai"
    assert (restored.pos().x(), restored.pos().y()) == pytest.approx((150, 30), abs=0.5)


def test_cancelled_empty_text_leaves_no_history(ctrl, graph):
    count = _stack(ctrl).count()
    _right_click(graph, 150, 30)
    graph.add_text_annotation().window.reject()

    assert _stack(ctrl).count() == count and _annotations(ctrl) == []


def test_curve_annotation_undo_removes_arrow(ctrl, graph):
    item = _curve_annotation(ctrl, graph)
    [annotation] = _annotations(ctrl)
    assert annotation.anchor_pos == pytest.approx(item.anchor_pos)
    parts = _arrow_parts(item)

    _stack(ctrl).undo()
    assert not any(p in graph.plot.items for p in (item,) + parts)

    _stack(ctrl).redo()
    restored = _item(ctrl, annotation.id)
    assert restored.anchor_pos == pytest.approx(annotation.anchor_pos)
    assert all(p in graph.plot.items for p in _arrow_parts(restored))


# ---------------- modifications ----------------

def _drag_text_with_mouse(graph, item, dx, dy, qapp):
    """Glisser-déposer réel du texte (événements souris dans la vue)."""
    view = graph.graph
    start_scene = item.mapToScene(item.boundingRect().center())
    start = view.mapFromScene(start_scene)
    end = start + QtCore.QPoint(dx, dy)
    QTest.mousePress(view.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=start)
    for i in range(1, 6):
        move = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove,
                                 QtCore.QPointF(start + (end - start) * i / 5),
                                 QtCore.Qt.MouseButton.NoButton,
                                 QtCore.Qt.MouseButton.LeftButton,
                                 QtCore.Qt.KeyboardModifier.NoModifier)
        QtCore.QCoreApplication.sendEvent(view.viewport(), move)
    QTest.mouseRelease(view.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=end)
    qapp.processEvents()


def test_dragging_text_is_one_undo_step(ctrl, graph, qapp):
    item = _free_text(ctrl, graph)
    [before] = _annotations(ctrl)
    count = _stack(ctrl).count()

    _drag_text_with_mouse(graph, item, 120, 60, qapp)

    assert _stack(ctrl).count() == count + 1
    [after] = _annotations(ctrl)
    assert after.id == before.id and after.pos != pytest.approx(before.pos)
    assert after.pos == pytest.approx((item.pos().x(), item.pos().y()))

    _stack(ctrl).undo()
    assert (item.pos().x(), item.pos().y()) == pytest.approx(before.pos)
    assert _annotations(ctrl) == [before]


def test_moving_anchor_is_undoable(ctrl, graph):
    item = _curve_annotation(ctrl, graph)
    [before] = _annotations(ctrl)

    handle = item.anchorHandle
    handle._press_pos = handle.pos()
    handle.setPos(QtCore.QPointF(100, 40))
    item.sigUserChanged.emit(item)            # fin du glissement (mouseReleaseEvent)

    [after] = _annotations(ctrl)
    assert after.anchor_pos == pytest.approx((100, 40))

    _stack(ctrl).undo()
    assert item.anchorHandle.pos().x() == pytest.approx(before.anchor_pos[0])
    assert item.lineItem.line().p2() == QtCore.QPointF(*before.anchor_pos)
    _stack(ctrl).redo()
    assert item.anchorHandle.pos() == QtCore.QPointF(100, 40)


def test_editing_text_is_undoable(ctrl, graph):
    item = _free_text(ctrl, graph)

    class DoubleClick:
        def accept(self): pass
    item.mouseDoubleClickEvent(DoubleClick())
    item.window.textEdit.setText("Fin de l'essai")
    item.window.accept()

    [annotation] = _annotations(ctrl)
    assert "Fin de l'essai" in annotation.html
    _stack(ctrl).undo()
    assert item.toPlainText() == "Début de l'essai"
    _stack(ctrl).redo()
    assert item.toPlainText() == "Fin de l'essai"


def test_cancelled_edit_leaves_no_history(ctrl, graph):
    item = _free_text(ctrl, graph)
    count = _stack(ctrl).count()

    class DoubleClick:
        def accept(self): pass
    item.mouseDoubleClickEvent(DoubleClick())
    item.window.reject()

    assert _stack(ctrl).count() == count


def test_delete_key_is_undoable(ctrl, graph):
    item = _curve_annotation(ctrl, graph)
    [annotation] = _annotations(ctrl)

    item.keyPressEvent(QtGui.QKeyEvent(QtCore.QEvent.Type.KeyPress,
                                       QtCore.Qt.Key.Key_Delete,
                                       QtCore.Qt.KeyboardModifier.NoModifier))
    assert _annotations(ctrl) == [] and _texts(graph) == []

    _stack(ctrl).undo()
    restored = _item(ctrl, annotation.id)
    assert _annotations(ctrl) == [annotation]
    assert restored.anchor_pos == pytest.approx(annotation.anchor_pos)

    _stack(ctrl).redo()
    assert _annotations(ctrl) == [] and _texts(graph) == []


# ---------------- sauvegarde du projet ----------------

def test_annotations_saved_and_reloaded(ctrl, graph, tmp_path):
    _free_text(ctrl, graph)
    _curve_annotation(ctrl, graph)
    saved = {a.id: a for a in _annotations(ctrl)}
    project = tmp_path / "project.json"
    ctrl.workspace.save(project)
    assert len(json.loads(project.read_text(encoding="utf-8"))
               ["workspace"]["annotations"]) == 2

    ctrl.import_ctrl.openProject(str(project))

    assert {a.id: a for a in _annotations(ctrl)} == saved
    view = ctrl.graph_ctrl.graph_tree_ctrl
    assert set(view.textItems) == set(saved)
    for annotation_id, annotation in saved.items():
        item = view.textItems[annotation_id]
        assert item in graph.plot.items
        assert (item.pos().x(), item.pos().y()) == pytest.approx(annotation.pos)
        if annotation.anchor_pos is None:
            assert item.lineItem is None
        else:
            assert item.anchorHandle.pos() == QtCore.QPointF(*annotation.anchor_pos)
    # une seule copie de chaque texte dans le graphique
    assert len(_texts(graph)) == 2
    assert _stack(ctrl).count() == 0


def test_reloaded_annotations_can_be_undone_after_edit(ctrl, graph, tmp_path):
    _free_text(ctrl, graph)
    project = tmp_path / "project.json"
    ctrl.workspace.save(project)
    ctrl.import_ctrl.openProject(str(project))
    [annotation] = _annotations(ctrl)
    item = _item(ctrl, annotation.id)

    item.keyPressEvent(QtGui.QKeyEvent(QtCore.QEvent.Type.KeyPress,
                                       QtCore.Qt.Key.Key_Delete,
                                       QtCore.Qt.KeyboardModifier.NoModifier))
    assert _annotations(ctrl) == []
    _stack(ctrl).undo()
    assert _annotations(ctrl) == [annotation]


def test_project_without_annotations(ctrl, graph, tmp_path):
    _free_text(ctrl, graph)
    project = tmp_path / "project.json"
    ctrl.workspace.save(project)
    data = json.loads(project.read_text(encoding="utf-8"))
    del data["workspace"]["annotations"]            # projet d'une version précédente
    project.write_text(json.dumps(data), encoding="utf-8")

    ctrl.import_ctrl.openProject(str(project))

    assert _annotations(ctrl) == [] and _texts(graph) == []


def test_annotation_dict_round_trip():
    annotation = TextAnnotation(html="<p>x</p>", pos=(1.0, 2.0), anchor_pos=(3.0, 4.0),
                                color="#ff123456", font="Times,8,-1,5,400,0,0,0,0,0")
    assert TextAnnotation.from_dict(json.loads(json.dumps(annotation.to_dict()))) == annotation
