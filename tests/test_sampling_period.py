# tests/test_sampling_period.py
"""
Période d'échantillonnage d'un fichier (ParameterTree > File editor > Sampling period) :
corrige la période lue à l'import (ex: .txt de NTC importé à 20 ms au lieu de 200 µs).
L'axe des temps est recalculé, les valeurs ne changent pas ; annulable.
"""
import numpy as np
import pytest

from helpers import add, load, nodes
from ressources.custom_types import qSignalType as T
from test_computed_channels import channel, dialog  # noqa: F401 (fixture)
from test_file_params import _select_file, _set


@pytest.fixture
def file_obj(ctrl, csv_files):
    return load(ctrl, csv_files[0])[0]                 # 600 points à 1 s


def _undo(ctrl):
    ctrl.workspace_ctrl.undo_stack.undo()


def test_sampling_period_shown_in_parameter_tree(ctrl, file_obj):
    param_tree = _select_file(ctrl, file_obj)
    assert param_tree.child("File editor", "Sampling period").value() == 1.0


def test_new_period_rescales_time_axis(ctrl, file_obj, qapp):
    values = [sig.y.copy() for sig in file_obj.signals]
    param_tree = _select_file(ctrl, file_obj)

    _set(param_tree, "Sampling period", 200e-6, qapp)

    for sig, before in zip(file_obj.signals, values):
        np.testing.assert_allclose(sig.x[:3], [0, 200e-6, 400e-6])
        assert sig.x[-1] == pytest.approx(599 * 200e-6)
        np.testing.assert_array_equal(sig.y, before)          # valeurs inchangées
        curve = ctrl.graph_ctrl.curves[sig]
        assert curve.xData[-1] == pytest.approx(599 * 200e-6)
    assert file_obj.display_name.endswith(" *")              # période modifiée

    _undo(ctrl)
    qapp.processEvents()                                     # panneau rechargé (différé)
    assert file_obj.sampling == 1.0 and file_obj.signals[0].x[-1] == 599.0
    assert not file_obj.display_name.endswith(" *")
    assert ctrl.param_ctrl.param.child("File editor", "Sampling period").value() == 1.0


def test_offset_and_truncation_apply_to_new_axis(ctrl, file_obj):
    ctrl._modify_file_params(_file_ctx(file_obj), {"sampling": 0.5, "offset": 10.0,
                                                   "start_x": 100.0})
    x = file_obj.signals[0].x
    assert x[0] == pytest.approx(110.0)                       # 200 points masqués à 0.5 s
    assert x[-1] == pytest.approx(10.0 + 599 * 0.5)


def _file_ctx(file_obj):
    from ressources.custom_items import SelectionContext, itemType
    return SelectionContext(role=itemType.FILE, signal=file_obj)


def test_file_parameters_are_undoable(ctrl, file_obj):
    """Décalage, troncature, étiquette : une entrée d'historique, comme la période."""
    ctrl._modify_file_params(_file_ctx(file_obj), {"offset": 100.0, "label": "200 W"})
    assert file_obj.signals[0].x[0] == 100.0 and file_obj.label == "200 W"
    _undo(ctrl)
    assert file_obj.signals[0].x[0] == 0.0 and file_obj.label == ""
    ctrl.workspace_ctrl.undo_stack.redo()
    assert file_obj.offset == 100.0


def test_thermal_model_recomputed(ctrl, file_obj):
    sig = file_obj.signals[0]                                 # échelon, tau = 80 s
    ctrl.workspace_ctrl.push(sig, add(T.MODEL))
    analysis = nodes(sig.analyses)[0]
    tau = analysis.results.tau

    ctrl._modify_file_params(_file_ctx(file_obj), {"sampling": 0.5})

    assert analysis.results.tau == pytest.approx(tau / 2, rel=1e-3)
    model = sig.derived_signals[0]
    assert model.x[0] == pytest.approx(0.0) and model.x[-1] < 600
    _undo(ctrl)
    assert analysis.results.tau == pytest.approx(tau, rel=1e-6)


def test_lowpass_follows_file_period(ctrl, file_obj):
    sig = file_obj.signals[0]
    ctrl.workspace_ctrl.push(sig, add(T.FILTER, {"cutoff": 0.01, "fs": 1.0, "order": 2}))
    ctrl.workspace_ctrl.push(sig, add(T.FILTER, {"cutoff": 0.01, "fs": 0.5, "order": 2}))

    ctrl._modify_file_params(_file_ctx(file_obj), {"sampling": 0.1})

    follows, manual = nodes(sig.pipeline)
    assert follows.get_param("fs") == pytest.approx(10.0)       # fs = 1 / période
    assert manual.get_param("fs") == 0.5                        # réglé à la main : inchangé
    tree_item = ctrl.model.find_item_by_object_id(follows.id)
    assert tree_item is not None and tree_item.obj is follows
    _undo(ctrl)
    assert nodes(sig.pipeline)[0].get_param("fs") == 1.0


def test_period_refused_when_a_filter_cannot_follow(ctrl, file_obj, warnings_shown):
    sig = file_obj.signals[0]
    ctrl.workspace_ctrl.push(sig, add(T.FILTER, {"cutoff": 0.4, "fs": 1.0, "order": 2}))
    count = ctrl.workspace_ctrl.undo_stack.count()

    ctrl._modify_file_params(_file_ctx(file_obj), {"sampling": 2.0})   # fs/2 = 0.25 Hz

    assert file_obj.sampling == 1.0
    assert ctrl.workspace_ctrl.undo_stack.count() == count
    assert "nouvelle période" in str(warnings_shown[0])


def test_computed_channel_follows_new_time_axis(ctrl, file_obj, dialog):
    p = channel(ctrl, dialog, file_obj, "steps(time; 0; 200; 3; 800)", name="P")
    np.testing.assert_allclose(p.y[[2, 3]], [200, 800])        # palier à t = 3 s
    ctrl._modify_file_params(_file_ctx(file_obj), {"sampling": 0.01})
    # même palier en temps : 300e échantillon à 10 ms
    np.testing.assert_allclose(p.y[[3, 299, 300]], [200, 200, 800])
    assert p.x[-1] == pytest.approx(5.99)


def test_period_saved_with_project(ctrl, file_obj, tmp_path):
    ctrl._modify_file_params(_file_ctx(file_obj), {"sampling": 200e-6})
    project = tmp_path / "period.json"
    ctrl.workspace.save(project)

    ctrl.import_ctrl.openProject(str(project))

    reloaded = ctrl.workspace.files[0]
    assert reloaded.sampling == 200e-6 and reloaded.imported_sampling == 1.0
    assert reloaded.signals[0].x[-1] == pytest.approx(599 * 200e-6)
    assert reloaded.display_name.endswith(" *")


def test_reset_button_restores_imported_period(ctrl, file_obj, qapp):
    file_obj.imported_sampling = 0.02                     # ex: .txt importé à 20 ms
    param = _select_file(ctrl, file_obj).child("File editor", "Sampling period")
    assert param.defaultValue() == 0.02
