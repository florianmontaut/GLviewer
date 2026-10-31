# tests/test_alignment.py
"""
Recalage d'un enregistrement dans le temps (« Align in time... ») : courbes du fichier
déplacées en direct (poignée, saisie, pas, points A / B), validation en une entrée de
l'historique, annulation.
"""
import numpy as np
import pytest
from PyQt6 import QtCore, QtGui

from controller.alignment_controller import FADED_OPACITY, format_duration
from ressources.custom_types import qSignalType as T, ActionModifier as M
from helpers import add, load


@pytest.fixture
def files(ctrl, csv_files):
    return list(load(ctrl, *csv_files))          # fileA, fileB : CH1 échelon, CH2 sinus


@pytest.fixture
def align(ctrl, files):
    """Recalage de fileB lancé depuis l'arbre."""
    item = ctrl.model.find_item(ctrl.model.root, files[1])
    ctrl.view.treefile.setCurrentIndex(ctrl.model.index_from_item(item))
    ctrl._action_concentrator(M.ADD_ACTION, T.ALIGN)
    return ctrl.alignment_ctrl


def _drawn_x(ctrl, sig):
    x, _ = ctrl.graph_ctrl.curves[sig].getOriginalDataset()
    return x


@pytest.mark.parametrize("seconds, text", [(0.25, "+0.250 s"), (-12, "-12.000 s"),
                                           (1634, "+27 min 14.0 s"),
                                           (-3725, "-1 h 02 min 05.0 s")])
def test_format_duration(seconds, text):
    assert format_duration(seconds) == text


def test_menu_enabled_on_file(ctrl, files):
    item = ctrl.model.find_item(ctrl.model.root, files[0])
    ctrl.view.treefile.setCurrentIndex(ctrl.model.index_from_item(item))
    action = ctrl.tree_ctrl.menu._actions[T.ALIGN]
    assert action.isEnabled() and action.text() == "Align in time..."


def test_start_fades_other_files(ctrl, files, align):
    assert align.active and align.file is files[1]
    assert align.panel is not None and align.panel.isVisibleTo(ctrl.view.statusBar())
    for sig in files[0].signals:
        assert ctrl.graph_ctrl.curves[sig].opacity() == pytest.approx(FADED_OPACITY)
    for sig in files[1].signals:
        assert ctrl.graph_ctrl.curves[sig].opacity() == 1.0


def test_live_shift_without_recompute(ctrl, files, align):
    sig = files[1].signals[0]
    align.set_delta(100.0)
    align._redraw()
    np.testing.assert_allclose(_drawn_x(ctrl, sig), sig.x + 100)
    np.testing.assert_allclose(_drawn_x(ctrl, files[0].signals[0]), files[0].signals[0].x)
    assert files[1].offset == 0 and ctrl.workspace_ctrl.undo_stack.count() == 0
    assert align.panel.offset.value() == 100 and align.panel.readable.text() == "+1 min 40.0 s"


def test_validate_one_undo_entry(ctrl, files, align):
    b = files[1]
    x_before = b.signals[0].x.copy()
    align.set_delta(-42.5)
    align.validate()
    assert not align.active and align.panel is None
    assert b.offset == pytest.approx(-42.5)
    np.testing.assert_allclose(b.signals[0].x, x_before - 42.5)
    np.testing.assert_allclose(_drawn_x(ctrl, b.signals[0]), x_before - 42.5)
    assert ctrl.workspace_ctrl.undo_stack.count() == 1
    assert all(c.opacity() == 1.0 for c in ctrl.graph_ctrl.curves.values())
    ctrl.workspace_ctrl.undo_stack.undo()
    assert b.offset == 0
    np.testing.assert_allclose(b.signals[0].x, x_before)


def test_cancel_restores(ctrl, files, align):
    b = files[1]
    align.set_delta(300.0)
    align._redraw()
    items = list(align._items)
    align.cancel()
    assert not align.active and b.offset == 0
    np.testing.assert_allclose(_drawn_x(ctrl, b.signals[0]), b.signals[0].x)
    assert all(item not in ctrl.graph_ctrl.plot.items for item in items)
    assert ctrl.workspace_ctrl.undo_stack.count() == 0
    assert all(c.opacity() == 1.0 for c in ctrl.graph_ctrl.curves.values())


def test_zero_shift_adds_nothing(ctrl, files, align):
    align.validate()
    assert ctrl.workspace_ctrl.undo_stack.count() == 0


def test_handle_drag(ctrl, files, align):
    align.handle.setValue(align._handle_origin + 30)
    assert align.delta == pytest.approx(30)
    assert align.panel.offset.value() == pytest.approx(30)


def test_step_buttons(ctrl, files, align):
    align.panel.step_buttons[60].click()
    align.panel.step_buttons[-10].click()
    assert align.delta == pytest.approx(50)


def test_spinbox_entry(ctrl, files, align):
    align.panel.offset.setValue(-1500)
    assert align.delta == -1500
    assert align.handle.value() == pytest.approx(align._handle_origin - 1500)


def test_points_a_and_b(ctrl, files, align):
    align.point_a.setValue(200.0)                # événement du fichier recalé
    align.point_b.setValue(260.0)                # même événement sur la référence
    align.align_points()
    assert align.delta == pytest.approx(60)
    assert align.point_a.value() == pytest.approx(260)   # A a suivi son événement
    align.set_delta(0)
    assert align.point_a.value() == pytest.approx(200)


def test_escape_and_enter_shortcuts(ctrl, files, align):
    align.set_delta(10)
    keys = [s.key() for s in align._shortcuts]
    escape = align._shortcuts[keys.index(QtGui.QKeySequence(QtCore.Qt.Key.Key_Escape))]
    escape.activated.emit()
    assert not align.active and files[1].offset == 0
    ctrl.start_alignment(files[1])
    align.set_delta(10)
    align._shortcuts[0].activated.emit()         # Entrée : validé
    assert files[1].offset == 10


def test_analysis_curves_and_computed_channels_follow(ctrl, files, align):
    b = files[1]
    align.cancel()
    ctrl.workspace_ctrl.push(b.signals[0], add(T.MODEL, {"model_range": [0.0, 599.0]}))
    ctrl.start_alignment(b)
    (derived,) = b.signals[0].derived_signals
    x_model = derived.x.copy()
    align.set_delta(20)
    align._redraw()
    np.testing.assert_allclose(_drawn_x(ctrl, derived), x_model + 20)
    align.validate()
    (derived,) = b.signals[0].derived_signals          # modèle recalculé une fois
    np.testing.assert_allclose(derived.x, x_model + 20)


def test_removed_file_cancels(ctrl, files, align):
    ctrl.remove_file(files[1], confirm=False)
    assert not align.active


def test_new_alignment_replaces_previous(ctrl, files, align):
    align.set_delta(5)
    ctrl.start_alignment(files[0])
    assert align.file is files[0] and align.delta == 0 and files[1].offset == 0
    assert ctrl.graph_ctrl.curves[files[1].signals[0]].opacity() == pytest.approx(
        FADED_OPACITY)


def test_simplified_keeps_peaks():
    from controller.alignment_controller import simplified
    x = np.arange(1_000_000, dtype=float)
    y = np.zeros_like(x)
    y[123_457] = 5.0                                     # pic isolé
    y[600_000:600_010] = np.nan                          # données manquantes
    xs, ys = simplified(x, y)
    assert xs.size <= 20_000 + 100
    assert np.nanmax(ys) == 5.0 and xs[0] == 0 and xs[-1] == x[-1]
    small_x, small_y = simplified(x[:100], y[:100])
    assert small_x.size == 100
