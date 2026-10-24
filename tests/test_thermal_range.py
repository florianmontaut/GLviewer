# tests/test_thermal_range.py
"""
Plage des données d'entrée du modèle thermique :
    - sélection sur le graphique AVANT la création (RangePicker)
    - édition ensuite avec les curseurs du ParameterTree
"""
import numpy as np
import pyqtgraph as pg
import pytest
from PyQt6 import QtWidgets

from ressources.custom_types import qSignalType as T, ActionModifier as M
from ressources.custom_items import SelectionContext, itemType
from ressources.custom_parameters import LinkedCursors
from helpers import add, load, nodes, make_request


@pytest.fixture
def step_file(tmp_path):
    """CH1 : 25 °C pendant 200 s puis échelon du 1er ordre (tau = 60 s, +20 °C)."""
    path = tmp_path / "step.csv"
    with open(path, "w") as f:
        f.write("Time;CH1;;CH2;\n")
        for i in range(600):
            y = 25 if i < 200 else 25 + 20 * (1 - np.exp(-(i - 200) / 60))
            f.write(f"{i};{y:.4f};{i};{20 + np.sin(i / 20):.4f};\n")
    return str(path).replace("\\", "/")


def _signal(ctrl, step_file):
    return load(ctrl, step_file)[0].signals[0]


def _menu_model(ctrl, sig):
    ctrl.view.treefile.setCurrentIndex(ctrl.model.signal_index(sig))
    ctrl._action_concentrator(M.ADD_ACTION, T.MODEL)


def _infinite_lines(ctrl):
    return [i for i in ctrl.graph_ctrl.plot.items if isinstance(i, pg.InfiniteLine)]


def _select_analysis(ctrl, sig):
    analysis = nodes(sig.analyses)[0]
    ctrl.param_ctrl.load_params(SelectionContext(role=itemType.ANALYSE, signal=sig,
                                                 analysis_id=analysis.id))
    return ctrl.param_ctrl.param.child("Model definition range")


# ---------------- modèle : plage effectivement utilisée ----------------

def test_fit_uses_model_range(ctrl, step_file):
    sig = _signal(ctrl, step_file)
    ctrl.workspace_ctrl.push(sig, add(T.MODEL, {"model_range": [200.0, 599.0]}))

    analysis = nodes(sig.analyses)[0]
    assert (analysis.t_start, analysis.t_end) == (200.0, 599.0)
    assert analysis.results.tau == pytest.approx(60, rel=0.02)
    # la courbe modèle commence au début de la plage
    assert sig.derived_signals[0].x[0] == pytest.approx(200.0)


def test_no_range_fits_whole_record(ctrl, step_file):
    sig = _signal(ctrl, step_file)
    ctrl.workspace_ctrl.push(sig, add(T.MODEL))

    analysis = nodes(sig.analyses)[0]
    assert (analysis.t_start, analysis.t_end) == (0.0, 599.0)


def test_range_is_clipped_to_data(ctrl, step_file):
    sig = _signal(ctrl, step_file)
    ctrl.workspace_ctrl.push(sig, add(T.MODEL, {"model_range": [200.0, 5000.0]}))
    assert nodes(sig.analyses)[0].t_end == 599.0


@pytest.mark.parametrize("bad_range", [[300.0, 200.0], [1000.0, 2000.0]])
def test_invalid_range_is_reported(ctrl, step_file, warnings_shown, bad_range):
    sig = _signal(ctrl, step_file)
    ctrl.workspace_ctrl.push(sig, add(T.MODEL, {"model_range": bad_range}))

    assert len(sig.analyses) == 0 and len(warnings_shown) == 1


def test_projection_duration(ctrl, step_file):
    sig = _signal(ctrl, step_file)
    ctrl.workspace_ctrl.push(sig, add(T.MODEL, {"model_range": [200.0, 400.0],
                                                "projection_duration": 1000.0,
                                                "projection_auto": False}))
    assert sig.derived_signals[0].x[-1] == pytest.approx(400.0 + 1000.0)


def test_legacy_range_means_whole_record(ctrl, step_file):
    from model.analysis.analysis_factory import AnalysisFactory
    for legacy in ([0, 1200], {"cursor_1": 0.0, "cursor_2": 0.0, "delta": 0.0}):
        node = AnalysisFactory().create_saved({"type": "MODEL",
                                               "params": {"model_range": legacy}})
        assert node.get_param("model_range") is None


# ---------------- création : sélection de la plage sur le graphique ----------------

def test_menu_shows_range_picker_without_creating_model(ctrl, step_file):
    sig = _signal(ctrl, step_file)
    _menu_model(ctrl, sig)

    picker = ctrl.graph_ctrl.range_picker
    assert picker.is_active and picker.region in ctrl.graph_ctrl.plot.items
    t_start, t_end = picker.current_range()
    assert 0 <= t_start < t_end <= 599
    assert len(sig.analyses) == 0
    assert ctrl.view.statusBar().currentMessage() == picker.HINT


def test_accepted_range_creates_model(ctrl, step_file):
    sig = _signal(ctrl, step_file)
    _menu_model(ctrl, sig)
    picker = ctrl.graph_ctrl.range_picker
    picker.region.setRegion((200.0, 599.0))

    picker.accept()

    analysis = nodes(sig.analyses)[0]
    assert analysis.get_param("model_range") == [200.0, 599.0]
    assert analysis.results.tau == pytest.approx(60, rel=0.02)
    assert not picker.is_active and picker.region is None
    assert not any(isinstance(i, pg.LinearRegionItem) for i in ctrl.graph_ctrl.plot.items)
    assert ctrl.view.statusBar().currentMessage() == ""
    # une seule entrée dans l'historique
    assert ctrl.workspace_ctrl.undo_stack.count() == 1


def test_cancelled_range_creates_nothing(ctrl, step_file):
    sig = _signal(ctrl, step_file)
    _menu_model(ctrl, sig)

    ctrl.graph_ctrl.range_picker.cancel()

    assert len(sig.analyses) == 0 and ctrl.workspace_ctrl.undo_stack.count() == 0
    assert not any(isinstance(i, pg.LinearRegionItem) for i in ctrl.graph_ctrl.plot.items)


def test_keyboard_shortcuts(ctrl, step_file):
    sig = _signal(ctrl, step_file)
    picker = ctrl.graph_ctrl.range_picker

    _menu_model(ctrl, sig)
    escape = [s for s in picker._shortcuts if s.key().toString() == "Esc"][0]
    escape.activated.emit()
    assert not picker.is_active and len(sig.analyses) == 0

    _menu_model(ctrl, sig)
    enter = [s for s in picker._shortcuts if s.key().toString() == "Return"][0]
    enter.activated.emit()
    assert not picker.is_active and len(sig.analyses) == 1


def test_double_click_inside_region_accepts(ctrl, step_file, qapp):
    sig = _signal(ctrl, step_file)
    _menu_model(ctrl, sig)
    picker = ctrl.graph_ctrl.range_picker
    picker.region.setRegion((200.0, 599.0))

    class FakeClick:
        def __init__(self, x):
            self._pos = ctrl.graph_ctrl.vb.mapViewToScene(pg.Point(x, 30))
        def double(self): return True
        def scenePos(self): return self._pos
        def accept(self): pass

    picker._on_mouse_clicked(FakeClick(100.0))     # hors de la zone : ignoré
    qapp.processEvents()
    assert picker.is_active

    picker._on_mouse_clicked(FakeClick(300.0))
    qapp.processEvents()
    assert not picker.is_active and len(sig.analyses) == 1


def test_new_selection_replaces_previous(ctrl, step_file):
    file_ = load(ctrl, step_file)[0]
    first, second = file_.signals
    _menu_model(ctrl, first)
    _menu_model(ctrl, second)

    regions = [i for i in ctrl.graph_ctrl.plot.items if isinstance(i, pg.LinearRegionItem)]
    assert len(regions) == 1 and ctrl.graph_ctrl.range_picker.signal is second


# ---------------- édition de la plage dans le ParameterTree ----------------

def test_parameter_tree_cursors_show_model_range(ctrl, step_file):
    sig = _signal(ctrl, step_file)
    ctrl.workspace_ctrl.push(sig, add(T.MODEL, {"model_range": [200.0, 500.0]}))

    cursors = _select_analysis(ctrl, sig)

    assert isinstance(cursors, LinkedCursors)
    assert cursors.positions() == [200.0, 500.0]
    assert cursors.child("show cursors").value()
    assert sorted(line.value() for line in _infinite_lines(ctrl)) == [200.0, 500.0]


def test_parameter_tree_cursors_default_to_whole_record(ctrl, step_file):
    sig = _signal(ctrl, step_file)
    ctrl.workspace_ctrl.push(sig, add(T.MODEL))
    assert _select_analysis(ctrl, sig).positions() == [0.0, 599.0]


def test_dragging_cursor_refits_only_on_release(ctrl, step_file, qapp):
    sig = _signal(ctrl, step_file)
    ctrl.workspace_ctrl.push(sig, add(T.MODEL, {"model_range": [100.0, 599.0]}))
    cursors = _select_analysis(ctrl, sig)
    stack = ctrl.workspace_ctrl.undo_stack

    line = cursors.cursors[0]
    for x in (120.0, 160.0, 200.0):          # déplacement : pas de recalcul
        line.setValue(x)
        qapp.processEvents()
    assert cursors.child("cursor 1").value() == 200.0
    assert stack.count() == 1

    line.sigPositionChangeFinished.emit(line)  # relâchement
    qapp.processEvents()

    assert stack.count() == 2
    analysis = nodes(sig.analyses)[0]
    assert analysis.get_param("model_range") == [200.0, 599.0]
    assert analysis.results.tau == pytest.approx(60, rel=0.02)
    # arbre reconstruit : curseurs toujours affichés, sans doublon dans le graphique
    assert ctrl.param_ctrl.param.child("Model definition range").positions() == [200.0, 599.0]
    assert sorted(l.value() for l in _infinite_lines(ctrl)) == [200.0, 599.0]

    stack.undo()
    assert nodes(sig.analyses)[0].get_param("model_range") == [100.0, 599.0]


def test_typed_cursor_value_refits(ctrl, step_file, qapp):
    sig = _signal(ctrl, step_file)
    ctrl.workspace_ctrl.push(sig, add(T.MODEL, {"model_range": [100.0, 599.0]}))
    cursors = _select_analysis(ctrl, sig)

    cursors.child("cursor 1").setValue(200.0)
    qapp.processEvents()

    assert nodes(sig.analyses)[0].get_param("model_range") == [200.0, 599.0]
    assert ctrl.workspace_ctrl.undo_stack.count() == 2


def test_toggling_cursors_does_not_refit(ctrl, step_file, qapp):
    sig = _signal(ctrl, step_file)
    ctrl.workspace_ctrl.push(sig, add(T.MODEL, {"model_range": [200.0, 500.0]}))
    analysis = nodes(sig.analyses)[0]
    cursors = _select_analysis(ctrl, sig)

    cursors.child("show cursors").setValue(False)
    qapp.processEvents()

    assert nodes(sig.analyses)[0] is analysis
    assert ctrl.workspace_ctrl.undo_stack.count() == 1
    assert _infinite_lines(ctrl) == []


def test_other_parameter_change_keeps_range(ctrl, step_file, qapp):
    sig = _signal(ctrl, step_file)
    ctrl.workspace_ctrl.push(sig, add(T.MODEL, {"model_range": [200.0, 500.0]}))
    _select_analysis(ctrl, sig)

    ctrl.param_ctrl.param.child("User estimated power input (W)").setValue(50.0)
    qapp.processEvents()

    analysis = nodes(sig.analyses)[0]
    assert analysis.get_param("power") == 50.0
    assert analysis.get_param("model_range") == [200.0, 500.0]


def test_selecting_another_item_removes_cursors(ctrl, step_file):
    sig = _signal(ctrl, step_file)
    ctrl.workspace_ctrl.push(sig, add(T.MODEL, {"model_range": [200.0, 500.0]}))
    _select_analysis(ctrl, sig)
    assert len(_infinite_lines(ctrl)) == 2

    ctrl.param_ctrl.load_params(SelectionContext(role=itemType.RAW, signal=sig))

    assert _infinite_lines(ctrl) == []


def test_graph_option_cursors_still_follow_their_axis(ctrl, qapp):
    """Curseurs généraux du graphique (même classe LinkedCursors)."""
    tree_ctrl = ctrl.graph_ctrl.graph_tree_ctrl
    vertical, horizontal = tree_ctrl.cursors_V, tree_ctrl.cursors_H
    assert vertical.child("cursor 1").value() == 1200.0
    assert horizontal.child("cursor 1").value() == 50.0

    vertical.cursors[1].setValue(4000.0)
    horizontal.cursors[1].setValue(80.0)
    qapp.processEvents()

    assert vertical.child("cursor 2").value() == 4000.0
    assert horizontal.child("cursor 2").value() == 80.0
    assert vertical.child("delta").value() == 2800.0
