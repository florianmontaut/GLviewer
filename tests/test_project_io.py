# tests/test_project_io.py
"""Sauvegarde d'un projet (.json) puis rechargement : filtres ET analyses."""
import json
import os

import numpy as np
import pytest
from PyQt6 import QtWidgets

from ressources.custom_types import qSignalType as T, ActionModifier as M, ImportMode, fileType
from ressources.custom_exceptions import JSONStructureError
from helpers import add, make_request, load, nodes


def _save_and_reload(ctrl, tmp_path):
    project = tmp_path / "project.json"
    ctrl.workspace.save(project)
    json.loads(project.read_text(encoding="utf-8"))  # JSON valide
    ctrl.import_ctrl.openProject(str(project))
    return ctrl.workspace


def _derived_curves(ctrl, sig):
    return [s for s in ctrl.graph_ctrl.curves
            if s.item_type.name == "DERIVED" and s.parent_signal is sig]


def test_thermal_analysis_round_trip(ctrl, csv_files, tmp_path):
    sig = load(ctrl, csv_files[0])[0].signals[0]
    ctrl.workspace_ctrl.push(sig, add(T.OFFSET, {"offset": 1.0}))
    ctrl.workspace_ctrl.push(sig, add(T.MODEL))
    ctrl.workspace_ctrl.push(sig, make_request(M.MODIFY_ACTION, T.MODEL, {"power": 50.0}, 0))
    before = nodes(sig.analyses)[0]
    expected_y = sig.derived_signals[0].y.copy()

    ws = _save_and_reload(ctrl, tmp_path)

    reloaded = ws.files[0].signals[0]
    analysis = nodes(reloaded.analyses)[0]
    assert analysis.action_type == T.MODEL
    assert list(reloaded.analyses.keys()) == [before.id] == [analysis.id]
    assert analysis.get_params() == before.get_params()
    assert analysis.results.tau == pytest.approx(before.results.tau)
    # signal dérivé recalculé : dans le graph et sous l'analyse dans l'arbre
    assert len(reloaded.derived_signals) == 1
    np.testing.assert_allclose(reloaded.derived_signals[0].y, expected_y)
    assert _derived_curves(ctrl, reloaded) == reloaded.derived_signals
    analysis_item = ctrl.model.find_item_by_object_id(analysis.id)
    assert [c.obj for c in analysis_item.children] == reloaded.derived_signals


def test_fft_analysis_round_trip(ctrl, csv_files, tmp_path):
    sig = load(ctrl, csv_files[0])[0].signals[1]
    ctrl.workspace_ctrl.push(sig, add(T.FFT, {"window": "hamming"}))
    assert len(sig.derived_signals) == 1

    ws = _save_and_reload(ctrl, tmp_path)

    reloaded = ws.files[0].signals[1]
    analysis = nodes(reloaded.analyses)[0]
    assert analysis.action_type == T.FFT and analysis.get_param("window") == "hamming"
    assert len(reloaded.derived_signals) == 1


def test_diff_between_files_round_trip(ctrl, csv_files, tmp_path):
    file_a, file_b = load(ctrl, *csv_files)
    sig_a, ref_b = file_a.signals[0], file_b.signals[1]
    ctrl.workspace_ctrl.push(sig_a, add(T.DIFF_EXT, {"reference": ref_b}))
    expected = sig_a.derived_signals[0].y.copy()

    ws = _save_and_reload(ctrl, tmp_path)

    reloaded = ws.files[0].signals[0]
    analysis = nodes(reloaded.analyses)[0]
    assert analysis.get_param("reference") is ws.files[1].signals[1]
    np.testing.assert_allclose(reloaded.derived_signals[0].y, expected)


def test_diff_filter_same_file_round_trip(ctrl, csv_files, tmp_path):
    file_a = load(ctrl, csv_files[0])[0]
    sig, ref = file_a.signals[0], file_a.signals[1]
    ctrl.workspace_ctrl.push(sig, add(T.DIFF, {"reference": ref}))
    expected = sig.y.copy()

    ws = _save_and_reload(ctrl, tmp_path)

    reloaded = ws.files[0].signals[0]
    assert nodes(reloaded.pipeline)[0].get_param("reference") is ws.files[0].signals[1]
    np.testing.assert_allclose(reloaded.y, expected)


def test_fft_with_default_params(ctrl, csv_files):
    """Depuis le menu contextuel, l'analyse est créée avec params = {}."""
    sig = load(ctrl, csv_files[0])[0].signals[1]
    ctrl.workspace_ctrl.push(sig, add(T.FFT))

    analysis = nodes(sig.analyses)[0]
    assert analysis.get_param("window") == "hann"
    assert len(sig.derived_signals) == 1


def test_reload_project_saved_before_ids(ctrl, csv_files, tmp_path):
    """Projets enregistrés avec l'ancienne version (pipeline = liste de dicts, sans id)."""
    from ressources import custom_struct_functions
    from PyQt6 import QtGui
    pen = custom_struct_functions.QPen_to_dict(QtGui.QPen())
    legacy = {"version": "1.0", "workspace": {"files": [{
        "file_type": "CSV", "import_params": {}, "address": csv_files[0],
        "signals": [
            {"name": "CH1", "visible": True, "pen": pen, "is_reference": False,
             "pipeline": [{"type": "OFFSET", "params": {"offset": 2.0}}],
             "analyses": [{}]},          # thermique sans résultat : sauvée {}
            {"name": "CH2", "visible": True, "pen": pen, "is_reference": False,
             "pipeline": [], "analyses": []},
        ]}]}}
    project = tmp_path / "legacy.json"
    project.write_text(json.dumps(legacy), encoding="utf-8")

    ctrl.import_ctrl.openProject(str(project))

    sig = ctrl.workspace.files[0].signals[0]
    assert [n.get_param("offset") for n in nodes(sig.pipeline)] == [2.0]
    assert all(key == node.id for key, node in sig.pipeline.items())
    assert len(sig.analyses) == 0
    np.testing.assert_allclose(sig.y, sig.raw_y + 2.0)


# ---------------- fichier de données introuvable ----------------

def _project_with_moved_file(ctrl, csv_files, tmp_path):
    load(ctrl, csv_files[0])
    project = tmp_path / "project.json"
    ctrl.workspace.save(project)
    os.rename(csv_files[0], csv_files[0] + ".moved")
    return project


def test_missing_data_file_keeps_later_imports_working(ctrl, csv_files, tmp_path):
    """Un projet en échec ne laisse pas l'import en mode « restauration »."""
    project = _project_with_moved_file(ctrl, csv_files, tmp_path)
    files_before = list(ctrl.workspace.files)

    with pytest.raises(JSONStructureError, match="introuvable"):
        ctrl.import_ctrl.openProject(str(project))

    assert ctrl.import_ctrl._from_project == ImportMode.INTERACTIVE
    assert ctrl.workspace.files == files_before          # workspace courant inchangé
    load(ctrl, csv_files[1])
    assert [f.name for f in ctrl.workspace.files] == ["fileA", "fileB"]


def test_missing_data_file_reported_from_menu(ctrl, csv_files, tmp_path, monkeypatch,
                                              warnings_shown):
    """Files > Load > Project : message d'erreur, pas d'import wizard sur le .json."""
    project = _project_with_moved_file(ctrl, csv_files, tmp_path)
    monkeypatch.setattr(QtWidgets.QFileDialog, "getOpenFileName",
                        lambda *a, **k: (str(project), ""))
    wizard = []
    monkeypatch.setattr(ctrl.import_ctrl, "ImportWizard", lambda *a, **k: wizard.append(a))

    ctrl.import_ctrl.load_file_dialog(fileType.JSON)

    assert not wizard
    assert len(warnings_shown) == 1 and "introuvable" in warnings_shown[0][2]


def test_missing_data_file_reported_from_recent_files(ctrl, csv_files, tmp_path,
                                                      warnings_shown):
    project = _project_with_moved_file(ctrl, csv_files, tmp_path)

    ctrl.import_ctrl.loaderSelect({"file_type": "JSON", "address": str(project),
                                   "import_params": {}})

    assert len(warnings_shown) == 1 and "introuvable" in warnings_shown[0][2]
