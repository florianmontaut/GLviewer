# tests/test_workspace.py
import numpy as np

from ressources.custom_types import qSignalType as T
from ressources.custom_exceptions import InvalidModelFit
from model.analysis.thermal import ThermalModelAnalysis
from helpers import add, load, nodes


def _undo_actions(ctrl):
    return [a for a in ctrl.view.actions() if a.text().startswith("Undo")]


def test_single_undo_stack_across_files(ctrl, csv_files):
    file_a = load(ctrl, csv_files[0])[0]
    workspace_ctrl = ctrl.workspace_ctrl
    sig_a = file_a.signals[0]
    workspace_ctrl.push(sig_a, add(T.OFFSET, {"offset": 1.0}))

    load(ctrl, csv_files[1])

    # l'historique de fileA survit au chargement de fileB
    assert ctrl.workspace_ctrl is workspace_ctrl
    assert ctrl.workspace_ctrl.undo_stack.count() == 1
    assert len(_undo_actions(ctrl)) == 1
    ctrl.workspace_ctrl.undo_stack.undo()
    assert nodes(sig_a.pipeline) == []


def test_loading_file_does_not_recompute_other_analyses(ctrl, csv_files):
    sig_a = load(ctrl, csv_files[0])[0].signals[0]
    ctrl.workspace_ctrl.push(sig_a, add(T.MODEL))
    assert len(sig_a.derived_signals) == 1

    load(ctrl, csv_files[1])

    assert len(sig_a.derived_signals) == 1
    derived_curves = [s for s in ctrl.graph_ctrl.curves if s.item_type.name == "DERIVED"]
    assert len(derived_curves) == 1


def test_thermal_analysis_add_and_undo(ctrl, csv_files):
    sig = load(ctrl, csv_files[0])[0].signals[0]
    ctrl.workspace_ctrl.push(sig, add(T.MODEL))

    assert len(sig.analyses) == 1
    res = nodes(sig.analyses)[0].results
    assert 70 < res.tau < 90 and 44 < res.T_inf < 46
    assert sig.derived_signals[0] in ctrl.graph_ctrl.curves

    ctrl.workspace_ctrl.undo_stack.undo()
    assert nodes(sig.analyses) == [] and sig.derived_signals == []


def test_failed_analysis_is_reported_and_not_pushed(ctrl, csv_files, warnings_shown, monkeypatch):
    sig = load(ctrl, csv_files[0])[0].signals[0]

    def bad_fit(self, *args, **kw):
        raise InvalidModelFit("fit impossible")
    monkeypatch.setattr(ThermalModelAnalysis, "run", bad_fit)

    ctrl.workspace_ctrl.push(sig, add(T.MODEL))

    assert ctrl.workspace_ctrl.undo_stack.count() == 0
    assert nodes(sig.analyses) == [] and sig.derived_signals == []
    assert len(warnings_shown) == 1 and "fit impossible" in warnings_shown[0][2]


def test_modify_analysis_and_undo(ctrl, csv_files):
    from ressources.custom_types import ActionModifier as M
    from helpers import make_request
    sig = load(ctrl, csv_files[0])[0].signals[0]
    ctrl.workspace_ctrl.push(sig, add(T.MODEL))
    first = nodes(sig.analyses)[0]

    ctrl.workspace_ctrl.push(sig, make_request(M.MODIFY_ACTION, T.MODEL, {"power": 50.0}, 0))
    assert nodes(sig.analyses)[0].get_param("power") == 50.0
    assert len(sig.derived_signals) == 1

    ctrl.workspace_ctrl.undo_stack.undo()
    assert nodes(sig.analyses)[0] is first and len(sig.derived_signals) == 1


def test_invalid_filter_params_are_reported(ctrl, csv_files, warnings_shown):
    sig = load(ctrl, csv_files[0])[0].signals[0]
    # fréquence de coupure > fs/2 : refusée par LowPassFilter.validate
    ctrl.workspace_ctrl.push(sig, add(T.FILTER, {"cutoff": 10.0, "fs": 1.0, "order": 2}))

    assert ctrl.workspace_ctrl.undo_stack.count() == 0 and nodes(sig.pipeline) == []
    assert len(warnings_shown) == 1


def test_project_save_and_reload_filters(ctrl, csv_files, tmp_path):
    files = load(ctrl, *csv_files)
    sig = files[0].signals[0]
    ctrl.workspace_ctrl.push(sig, add(T.OFFSET, {"offset": 2.0}))
    ctrl.workspace_ctrl.push(sig, add(T.AVG, {"window": 3}))
    expected_y = sig.y.copy()
    project = tmp_path / "project.json"
    ctrl.workspace.save(project)

    ctrl.import_ctrl.openProject(str(project))

    ws = ctrl.workspace
    assert [f.name for f in ws.files] == ["fileA", "fileB"]
    reloaded = ws.files[0].signals[0]
    assert reloaded is not sig
    assert [n.action_type for n in nodes(reloaded.pipeline)] == [T.OFFSET, T.AVG]
    np.testing.assert_allclose(reloaded.y, expected_y)
    # le graph ne contient plus que les courbes du projet rechargé
    assert set(ctrl.graph_ctrl.curves) == {s for f in ws.files for s in f.signals}
    assert ctrl.workspace_ctrl.undo_stack.count() == 0
