# tests/test_time_shift.py
"""
Décalage temporel (TimeShiftFilter) et principe du pipeline : les filtres sont des
calques, les données brutes du fichier ne sont jamais modifiées.
"""
import numpy as np
import pytest

from ressources.custom_types import qSignalType as T, ActionModifier as M
from helpers import add, load, nodes, make_request


def _shift(ctrl, sig, seconds):
    ctrl.workspace_ctrl.push(sig, add(T.OFFSET_X, {"shift_seconds": seconds}))


@pytest.fixture
def sig(ctrl, csv_files):
    return load(ctrl, csv_files[0])[0].signals[0]          # x = 0..599 s


def _raw_snapshot(sig):
    return sig.file.data.copy(), sig.raw_x.copy()


# ---------------- calque : les données brutes ne bougent pas ----------------

def test_time_shift_moves_x_only(ctrl, sig):
    data_before, raw_x_before = _raw_snapshot(sig)
    y_before = sig.y.copy()

    _shift(ctrl, sig, 100.0)

    np.testing.assert_allclose(sig.x, raw_x_before + 100.0)
    np.testing.assert_allclose(sig.y, y_before)
    # données brutes intactes : DataFrame du fichier et axe des temps brut
    assert sig.file.data.equals(data_before)
    np.testing.assert_allclose(sig.raw_x, raw_x_before)
    # la courbe affichée suit le calque
    np.testing.assert_allclose(ctrl.graph_ctrl.curves[sig].xData, raw_x_before + 100.0)


def test_other_signals_of_the_file_are_not_shifted(ctrl, sig):
    other = sig.file.signals[1]
    _shift(ctrl, sig, 100.0)
    np.testing.assert_allclose(other.x, sig.raw_x)


def test_undo_redo_and_removal_restore_raw(ctrl, sig):
    raw_x = sig.raw_x.copy()
    _shift(ctrl, sig, 100.0)

    ctrl.workspace_ctrl.undo_stack.undo()
    np.testing.assert_allclose(sig.x, raw_x)
    ctrl.workspace_ctrl.undo_stack.redo()
    np.testing.assert_allclose(sig.x, raw_x + 100.0)

    ctrl.workspace_ctrl.push(sig, make_request(M.REMOVE_ACTION, T.OFFSET_X, index=0))
    np.testing.assert_allclose(sig.x, raw_x)


def test_layers_accumulate_in_order(ctrl, sig):
    raw_x, raw_y = sig.raw_x.copy(), sig.raw_y
    _shift(ctrl, sig, 100.0)
    ctrl.workspace_ctrl.push(sig, add(T.OFFSET, {"offset": 2.0}))
    _shift(ctrl, sig, -30.0)

    np.testing.assert_allclose(sig.x, raw_x + 70.0)
    np.testing.assert_allclose(sig.y, raw_y + 2.0)


def test_modify_shift(ctrl, sig):
    _shift(ctrl, sig, 100.0)
    ctrl.workspace_ctrl.push(sig, make_request(M.MODIFY_ACTION, T.OFFSET_X,
                                               {"shift_seconds": 250.0}, 0))
    assert sig.x[0] == 250.0
    ctrl.workspace_ctrl.undo_stack.undo()
    assert sig.x[0] == 100.0


def test_filtered_x_is_read_only(ctrl, sig):
    _shift(ctrl, sig, 100.0)
    with pytest.raises(ValueError):
        sig.x[0] = 0.0


def test_file_time_offset_invalidates_pipeline_cache(ctrl, sig):
    _shift(ctrl, sig, 100.0)
    _ = sig.x
    sig.file.set_offset(1000.0)
    assert sig.x[0] == 1100.0


def test_zoom_limits_follow_shift(ctrl, sig):
    _shift(ctrl, sig, 10000.0)
    ctrl.graph_ctrl.vb.setRange(xRange=(-1e9, 1e9), padding=0)
    x0, x1 = ctrl.graph_ctrl.vb.viewRange()[0]
    assert x1 >= 10599


# ---------------- curseur ----------------

def test_nearest_value(ctrl, sig):
    xs, ys = sig.x, sig.y
    for x in (-50.0, 0.0, 0.4, 0.6, 123.49, 123.51, 598.7, 5000.0):
        i = int(np.argmin(np.abs(xs - x)))
        assert sig.nearest_value(x) == pytest.approx(ys[i])


def test_cursor_column_uses_filtered_values(ctrl, sig):
    """Régression : la colonne lisait le DataFrame brut (offset Y ignoré)."""
    ctrl.workspace_ctrl.push(sig, add(T.OFFSET, {"offset": 10.0}))
    _shift(ctrl, sig, 100.0)

    ctrl.model.updateCursorVal(300.0)

    other = sig.file.signals[1]
    # sig décalé de 100 s : à t = 300 s on lit l'échantillon brut n°200, + 10 °C
    assert ctrl.model.cursor_values[sig] == pytest.approx(sig.raw_y[200] + 10.0)
    assert ctrl.model.cursor_values[other] == pytest.approx(other.raw_y[300])


def test_cursor_snap_uses_filtered_values(ctrl, sig):
    _shift(ctrl, sig, 100.0)
    emitted = []
    ctrl.cursor_ctrl.cursor_moved.connect(emitted.append)
    ctrl.cursor_ctrl.set_snap(True)
    ctrl.cursor_ctrl.set_signal(sig)

    ctrl.cursor_ctrl.update_x(300.0)

    assert emitted[-1] == [300.0, pytest.approx(sig.raw_y[200])]


# ---------------- différence entre voies ----------------

def test_diff_with_shifted_reference_is_interpolated(ctrl, sig):
    ref = sig.file.signals[1]
    _shift(ctrl, ref, 100.0)
    ctrl.workspace_ctrl.push(sig, add(T.DIFF, {"reference": ref}))

    expected = sig.raw_y - np.interp(sig.x, ref.x, ref.y, left=np.nan, right=np.nan)
    np.testing.assert_allclose(sig.y, expected)
    assert np.isnan(sig.y[:100]).all()            # référence absente avant t = 100 s
    np.testing.assert_allclose(sig.y[100:], sig.raw_y[100:] - ref.raw_y[:500])


def test_diff_on_same_time_axis_unchanged(ctrl, sig):
    ref = sig.file.signals[1]
    ctrl.workspace_ctrl.push(sig, add(T.DIFF, {"reference": ref}))
    np.testing.assert_allclose(sig.y, sig.raw_y - ref.raw_y)


# ---------------- menu et sauvegarde ----------------

def test_x_offset_in_context_menus(ctrl, sig):
    for menu in (ctrl.tree_ctrl.menu.menu, ctrl.graph_ctrl.menu.menu):
        assert "Add an X offset" in [a.text() for a in menu.actions()]

    ctrl.view.treefile.setCurrentIndex(ctrl.model.signal_index(sig))
    ctrl._action_concentrator(M.ADD_ACTION, T.OFFSET_X)
    assert [n.action_type for n in nodes(sig.pipeline)] == [T.OFFSET_X]


def test_time_shift_saved_in_project(ctrl, sig, tmp_path):
    _shift(ctrl, sig, 100.0)
    project = tmp_path / "project.json"
    ctrl.workspace.save(project)

    ctrl.import_ctrl.openProject(str(project))

    reloaded = ctrl.workspace.files[0].signals[0]
    np.testing.assert_allclose(reloaded.x, reloaded.raw_x + 100.0)
