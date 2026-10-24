# tests/test_analysis_refresh.py
"""
Les analyses (modèle thermique, FFT, différence entre fichiers) sont recalculées quand
leurs données d'entrée changent : filtres, undo/redo, décalage ou troncature du fichier,
signal de référence.
"""
import numpy as np
import pytest
from PyQt6 import QtCore

from ressources.custom_types import qSignalType as T, ActionModifier as M
from helpers import add, load, nodes, make_request


@pytest.fixture
def sig(ctrl, csv_files):
    s = load(ctrl, csv_files[0])[0].signals[0]          # échelon tau = 80 s
    ctrl.workspace_ctrl.push(s, add(T.MODEL, {"model_range": [0.0, 400.0]}))
    return s


def _model(sig):
    [derived] = [d for d in sig.derived_signals if d.metadata.get("type") == "thermal_model"]
    return derived


def _derived_curves(ctrl, sig):
    return [s for s in ctrl.graph_ctrl.curves
            if s.item_type.name == "DERIVED" and s.parent_signal is sig]


def _analysis_item(ctrl, sig, analysis):
    return ctrl.model.find_item_by_object_id(analysis.id, ctrl.model.find_signal_item(sig))


def _check_consistent(ctrl, sig):
    """Arbre et graph reflètent exactement sig.derived_signals."""
    assert sorted(map(id, _derived_curves(ctrl, sig))) == sorted(map(id, sig.derived_signals))
    for analysis in nodes(sig.analyses):
        item = _analysis_item(ctrl, sig, analysis)
        expected = [d for d in sig.derived_signals
                    if d.metadata.get("analysis_id") == analysis.id]
        assert [c.obj for c in item.children] == expected


# ---------------- filtres ----------------

def test_filter_recomputes_model(ctrl, sig):
    before = _model(sig)
    t_inf = nodes(sig.analyses)[0].results.T_inf

    ctrl.workspace_ctrl.push(sig, add(T.OFFSET, {"offset": 10.0}))

    after = _model(sig)
    assert after is not before
    assert nodes(sig.analyses)[0].results.T_inf == pytest.approx(t_inf + 10.0, abs=0.01)
    np.testing.assert_allclose(after.y, before.y + 10.0, atol=0.01)
    np.testing.assert_allclose(ctrl.graph_ctrl.curves[after].yData, after.y)
    _check_consistent(ctrl, sig)


def test_undo_redo_filter_recomputes_model(ctrl, sig):
    y0 = _model(sig).y.copy()
    ctrl.workspace_ctrl.push(sig, add(T.OFFSET, {"offset": 10.0}))

    ctrl.workspace_ctrl.undo_stack.undo()
    np.testing.assert_allclose(_model(sig).y, y0, atol=0.01)
    ctrl.workspace_ctrl.undo_stack.redo()
    np.testing.assert_allclose(_model(sig).y, y0 + 10.0, atol=0.01)
    _check_consistent(ctrl, sig)


def test_time_shift_moves_model(ctrl, sig):
    x0 = _model(sig).x.copy()
    ctrl.workspace_ctrl.push(sig, add(T.OFFSET_X, {"shift_seconds": 100.0}))
    # la plage [0, 400] ne couvre plus que [100, 400] des données décalées
    assert nodes(sig.analyses)[0].t_start == 100.0
    assert _model(sig).x[0] == pytest.approx(100.0)
    assert not np.allclose(_model(sig).x[:10], x0[:10])


def test_unrelated_change_does_not_recompute(ctrl, sig):
    before = _model(sig)
    other = sig.file.signals[1]
    ctrl.workspace_ctrl.push(other, add(T.OFFSET, {"offset": 10.0}))
    assert _model(sig) is before


def test_new_analysis_is_not_computed_twice(ctrl, sig, monkeypatch):
    from model.analysis.fft import FFTAnalysis
    calls = []
    original = FFTAnalysis.compute
    monkeypatch.setattr(FFTAnalysis, "compute",
                        lambda self, s: (calls.append(1), original(self, s))[1])
    ctrl.workspace_ctrl.push(sig, add(T.FFT))
    assert len(calls) == 1


# ---------------- paramètres du fichier ----------------

def _file_param(ctrl, sig, name, value, qapp):
    item = ctrl.model.find_item(ctrl.model.root, sig.file)
    ctrl.view.treefile.setCurrentIndex(ctrl.model.index_from_item(item))
    ctrl.param_ctrl.param.child("File editor", name).setValue(value)
    qapp.processEvents()


def test_truncation_recomputes_model(ctrl, sig, qapp):
    _file_param(ctrl, sig, "Truncate left", 100.0, qapp)
    assert nodes(sig.analyses)[0].t_start == 100.0
    assert _model(sig).x[0] == pytest.approx(100.0)
    _check_consistent(ctrl, sig)


def test_failed_recompute_is_reported(ctrl, sig, qapp):
    """Troncature ne laissant que 3 points dans la plage [0, 400] : fit impossible,
    courbe retirée, analyse ⚠."""
    _file_param(ctrl, sig, "Truncate left", 398.0, qapp)

    analysis = nodes(sig.analyses)[0]
    assert analysis.error and sig.derived_signals == [] and _derived_curves(ctrl, sig) == []
    index = ctrl.model.index_from_item(_analysis_item(ctrl, sig, analysis))
    assert ctrl.model.data(index, QtCore.Qt.ItemDataRole.DisplayRole).endswith("⚠")
    assert "Analyse non recalculée" in ctrl.model.data(index, QtCore.Qt.ItemDataRole.ToolTipRole)
    assert "non recalculée" in ctrl.view.statusBar().currentMessage()

    # données de nouveau valides : recalcul automatique, erreur effacée
    _file_param(ctrl, sig, "Truncate left", 0.0, qapp)
    assert analysis.error is None and len(sig.derived_signals) == 1
    assert not ctrl.model.data(index, QtCore.Qt.ItemDataRole.DisplayRole).endswith("⚠")
    _check_consistent(ctrl, sig)


# ---------------- commandes d'analyse après recalcul ----------------

def test_undo_add_analysis_after_recompute(ctrl, sig):
    ctrl.workspace_ctrl.push(sig, add(T.OFFSET, {"offset": 10.0}))   # modèle recalculé
    stack = ctrl.workspace_ctrl.undo_stack
    stack.undo()                    # filtre
    stack.undo()                    # modèle
    assert sig.derived_signals == [] and _derived_curves(ctrl, sig) == []


def test_modify_and_remove_analysis_after_recompute(ctrl, sig):
    ctrl.workspace_ctrl.push(sig, add(T.OFFSET, {"offset": 10.0}))
    ctrl.workspace_ctrl.push(sig, make_request(M.MODIFY_ACTION, T.MODEL, {"power": 50.0}, 0))
    assert len(sig.derived_signals) == 1
    _check_consistent(ctrl, sig)

    ctrl.workspace_ctrl.undo_stack.undo()
    assert len(sig.derived_signals) == 1
    _check_consistent(ctrl, sig)

    ctrl.workspace_ctrl.push(sig, make_request(M.REMOVE_ACTION, T.MODEL, index=0))
    assert sig.derived_signals == [] and _derived_curves(ctrl, sig) == []
    ctrl.workspace_ctrl.push(sig, add(T.OFFSET, {"offset": 1.0}))
    ctrl.workspace_ctrl.undo_stack.undo()           # filtre
    ctrl.workspace_ctrl.undo_stack.undo()           # suppression du modèle
    assert len(sig.derived_signals) == 1
    _check_consistent(ctrl, sig)


# ---------------- autres analyses ----------------

def test_fft_recomputed_after_filter(ctrl, csv_files):
    s = load(ctrl, csv_files[0])[0].signals[1]
    ctrl.workspace_ctrl.push(s, add(T.FFT))
    before = s.derived_signals[0].y.copy()
    ctrl.workspace_ctrl.push(s, add(T.OFFSET, {"offset": 5.0}))
    assert not np.allclose(s.derived_signals[0].y, before)


def test_diff_between_files_follows_reference(ctrl, csv_files):
    file_a, file_b = load(ctrl, *csv_files)
    sig_a, ref = file_a.signals[0], file_b.signals[0]
    ctrl.workspace_ctrl.push(sig_a, add(T.DIFF_EXT, {"reference": ref}))
    before = sig_a.derived_signals[0].y.copy()

    ctrl.workspace_ctrl.push(ref, add(T.OFFSET, {"offset": 3.0}))

    np.testing.assert_allclose(sig_a.derived_signals[0].y, before - 3.0, atol=1e-9)
    _check_consistent(ctrl, sig_a)


# ---------------- projet ----------------

def test_project_reload_with_failing_analysis(ctrl, sig, tmp_path, qapp):
    """Une analyse qui échoue au rechargement est signalée sans bloquer le chargement."""
    sig.file.set_params({"start_x": 398.0})
    project = tmp_path / "project.json"
    ctrl.workspace.save(project)

    ctrl.import_ctrl.openProject(str(project))

    reloaded = ctrl.workspace.files[0].signals[0]
    assert len(reloaded.analyses) == 1 and nodes(reloaded.analyses)[0].error
    assert reloaded.derived_signals == []


# ---------------- la plage du modèle suit les données décalées ----------------

def test_model_range_follows_file_offset(ctrl, sig, qapp):
    analysis = nodes(sig.analyses)[0]
    tau, x0 = analysis.results.tau, _model(sig).x.copy()

    _file_param(ctrl, sig, "Time offset", 5000.0, qapp)

    analysis = nodes(sig.analyses)[0]
    assert analysis.error is None
    assert (analysis.t_start, analysis.t_end) == (5000.0, 5400.0)
    assert analysis.results.tau == pytest.approx(tau)          # mêmes échantillons
    np.testing.assert_allclose(_model(sig).x, x0 + 5000.0)
    assert analysis.get_param("model_range") == [0.0, 400.0]   # temps de l'enregistrement


def test_model_range_follows_time_shift_filter(ctrl, sig):
    tau = nodes(sig.analyses)[0].results.tau
    ctrl.workspace_ctrl.push(sig, add(T.OFFSET_X, {"shift_seconds": 100.0}))
    analysis = nodes(sig.analyses)[0]
    assert (analysis.t_start, analysis.t_end) == (100.0, 500.0)
    assert analysis.results.tau == pytest.approx(tau)


def test_range_picked_on_shifted_signal(ctrl, csv_files):
    s = load(ctrl, csv_files[0])[0].signals[0]
    s.file.set_params({"offset": 1000.0})
    ctrl.view.treefile.setCurrentIndex(ctrl.model.signal_index(s))
    ctrl._action_concentrator(M.ADD_ACTION, T.MODEL)
    picker = ctrl.graph_ctrl.range_picker
    picker.region.setRegion((1100.0, 1400.0))             # temps affiché
    picker.accept()

    analysis = nodes(s.analyses)[0]
    assert analysis.get_param("model_range") == pytest.approx([100.0, 400.0])
    assert (analysis.t_start, analysis.t_end) == (1100.0, 1400.0)


def test_parameter_tree_shows_and_edits_displayed_range(ctrl, sig, qapp):
    from ressources.custom_items import SelectionContext, itemType
    sig.file.set_params({"offset": 1000.0})
    ctrl._refresh_derived()
    analysis = nodes(sig.analyses)[0]
    ctrl.param_ctrl.load_params(SelectionContext(role=itemType.ANALYSE, signal=sig,
                                                 analysis_id=analysis.id))
    cursors = ctrl.param_ctrl.param.child("Model definition range")
    assert cursors.positions() == [1000.0, 1400.0]

    cursors.child("cursor 1").setValue(1100.0)            # saisie en temps affiché
    qapp.processEvents()

    updated = nodes(sig.analyses)[0]
    assert updated.get_param("model_range") == pytest.approx([100.0, 400.0])
    assert (updated.t_start, updated.t_end) == (1100.0, 1400.0)


def test_project_keeps_record_time_range(ctrl, sig, tmp_path):
    sig.file.set_params({"offset": 1000.0})
    ctrl._refresh_derived()
    project = tmp_path / "project.json"
    ctrl.workspace.save(project)

    ctrl.import_ctrl.openProject(str(project))

    analysis = nodes(ctrl.workspace.files[0].signals[0].analyses)[0]
    assert analysis.get_param("model_range") == [0.0, 400.0]
    assert (analysis.t_start, analysis.t_end) == (1000.0, 1400.0)


def test_legacy_range_in_displayed_time(ctrl, sig, tmp_path):
    """Projet d'avant la plage en temps de l'enregistrement : plage en temps affiché."""
    import json
    sig.file.set_params({"offset": 1000.0})
    ctrl._refresh_derived()
    project = tmp_path / "project.json"
    ctrl.workspace.save(project)
    data = json.loads(project.read_text(encoding="utf-8"))
    [entry] = data["workspace"]["files"][0]["signals"][0]["analyses"]
    params = entry[1]["params"]
    params["model_range"] = [1100.0, 1400.0]
    del params["range_origin"]
    project.write_text(json.dumps(data), encoding="utf-8")

    ctrl.import_ctrl.openProject(str(project))

    analysis = nodes(ctrl.workspace.files[0].signals[0].analyses)[0]
    assert (analysis.t_start, analysis.t_end) == (1100.0, 1400.0)
    assert analysis.get_param("model_range") == pytest.approx([100.0, 400.0])
