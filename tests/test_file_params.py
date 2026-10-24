# tests/test_file_params.py
"""Paramètres d'un fichier (ParameterTree) : décalage temporel et troncatures."""
import numpy as np
import pytest
from PyQt6 import QtCore

from ressources.custom_types import qSignalType as T
from ressources.custom_items import itemType
from helpers import add, load


@pytest.fixture
def file_obj(ctrl, csv_files):
    return load(ctrl, csv_files[0])[0]                 # 600 points, x = 0..599 s


def _select_file(ctrl, file_obj):
    item = ctrl.model.find_item(ctrl.model.root, file_obj)
    ctrl.view.treefile.setCurrentIndex(ctrl.model.index_from_item(item))
    return ctrl.param_ctrl.param


def _set(param_tree, name, value, qapp):
    param_tree.child("File editor", name).setValue(value)
    qapp.processEvents()


# ---------------- sélection dans l'arbre ----------------

def test_selecting_file_shows_its_parameters(ctrl, file_obj):
    param_tree = _select_file(ctrl, file_obj)

    assert param_tree is not None and param_tree.name() == file_obj.display_name
    assert param_tree.child("File name").value() == file_obj.name
    for name in ("Time offset", "Truncate left", "Truncate right"):
        assert param_tree.child("File editor", name).value() == 0.0


def test_file_selection_context(ctrl, file_obj):
    item = ctrl.model.find_item(ctrl.model.root, file_obj)
    ctx = item.to_selection_context()
    assert ctx.role == itemType.FILE and ctx.signal is file_obj


def test_selecting_signal_after_file_shows_signal_parameters(ctrl, file_obj):
    _select_file(ctrl, file_obj)
    sig = file_obj.signals[0]
    ctrl.view.treefile.setCurrentIndex(ctrl.model.signal_index(sig))
    assert ctrl.param_ctrl.param.child("Curve name").value() == sig.name


# ---------------- décalage temporel du fichier ----------------

def test_time_offset_from_parameter_tree(ctrl, file_obj, qapp):
    param_tree = _select_file(ctrl, file_obj)

    _set(param_tree, "Time offset", 1000.0, qapp)

    for sig in file_obj.signals:
        assert sig.x[0] == 1000.0
        assert ctrl.graph_ctrl.curves[sig].xData[0] == 1000.0


# ---------------- troncatures ----------------

def test_truncation_is_a_layer(ctrl, file_obj, qapp):
    sig = file_obj.signals[0]
    data_before = file_obj.data.copy()
    param_tree = _select_file(ctrl, file_obj)

    _set(param_tree, "Truncate left", 100.0, qapp)
    _set(ctrl.param_ctrl.param, "Truncate right", 50.0, qapp)

    np.testing.assert_allclose(sig.x[[0, -1]], [100.0, 549.0])
    np.testing.assert_allclose(sig.y, sig.raw_y[100:550])
    np.testing.assert_allclose(ctrl.graph_ctrl.curves[sig].xData[[0, -1]], [100.0, 549.0])
    assert file_obj.data.equals(data_before)                 # données brutes intactes

    _set(ctrl.param_ctrl.param, "Truncate left", 0.0, qapp)
    _set(ctrl.param_ctrl.param, "Truncate right", 0.0, qapp)
    np.testing.assert_allclose(sig.x[[0, -1]], [0.0, 599.0])


def test_truncation_with_filters_and_time_shift(ctrl, file_obj):
    sig = file_obj.signals[0]
    ctrl.workspace_ctrl.push(sig, add(T.OFFSET, {"offset": 2.0}))
    ctrl.workspace_ctrl.push(sig, add(T.OFFSET_X, {"shift_seconds": 1000.0}))

    file_obj.set_params({"start_x": 100.0})

    # la troncature s'applique sur l'enregistrement, avant les filtres
    np.testing.assert_allclose(sig.x[0], 1100.0)
    np.testing.assert_allclose(sig.y, sig.raw_y[100:] + 2.0)


def test_truncation_longer_than_record_masks_nothing(file_obj):
    file_obj.set_params({"start_x": 400.0, "stop_x": 400.0})
    assert len(file_obj.signals[0].x) == 600


def test_offset_and_truncation_combined(file_obj):
    file_obj.set_params({"offset": 50.0, "start_x": 10.0})
    np.testing.assert_allclose(file_obj.signals[0].x[0], 60.0)


def test_cursor_value_respects_truncation(ctrl, file_obj):
    sig = file_obj.signals[0]
    file_obj.set_params({"start_x": 100.0})
    ctrl.model.updateCursorVal(0.0)                  # avant la fenêtre : 1er point conservé
    assert ctrl.model.cursor_values[sig] == pytest.approx(sig.raw_y[100])


# ---------------- sauvegarde ----------------

def test_file_parameters_saved_in_project(ctrl, file_obj, tmp_path):
    file_obj.set_params({"offset": 1000.0, "start_x": 100.0, "stop_x": 50.0})
    project = tmp_path / "project.json"
    ctrl.workspace.save(project)

    ctrl.import_ctrl.openProject(str(project))

    reloaded = ctrl.workspace.files[0]
    assert (reloaded.offset, reloaded.start_x, reloaded.stop_x) == (1000.0, 100.0, 50.0)
    np.testing.assert_allclose(reloaded.signals[0].x[[0, -1]], [1100.0, 1549.0])
    assert ctrl.graph_ctrl.curves[reloaded.signals[0]].xData[0] == 1100.0
