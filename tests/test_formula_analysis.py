# tests/test_formula_analysis.py
"""
Analyse « Formula » : courbe calculée par une formule sur les voies ([T AMB], [200 W:T AMB],
CH3, time), base de temps du fichier hôte ou période propre, recalcul, sauvegarde.
"""
import numpy as np
import pytest
from PyQt6 import QtWidgets

from conftest import _write_xy_csv
from ressources.custom_items import ActionRequest
from ressources.custom_types import qSignalType as T, ActionModifier as M
from helpers import add, load, make_request, nodes


@pytest.fixture
def files(ctrl, csv_files):
    return list(load(ctrl, *csv_files))          # fileA, fileB : CH1 échelon, CH2 sinus


def formula(ctrl, sig, text, **params):
    request = ActionRequest(action_modifier=M.ADD_ACTION, action_type=T.FORMULA,
                            params={"formula": text, **params}, index=None)
    return ctrl.workspace_ctrl.push(sig, request)


def result(sig):
    (derived,) = [d for d in sig.derived_signals if d.metadata.get("type") == "formula"]
    return derived


def test_formula_on_host_channels(ctrl, files):
    ch1, ch2 = files[0].signals
    assert formula(ctrl, ch1, "[CH1] - [CH2]", name="Ecart", unit="K")
    derived = result(ch1)
    np.testing.assert_allclose(derived.x, ch1.x)
    np.testing.assert_allclose(derived.y, ch1.y - ch2.y)
    assert (derived.name, derived.unit) == ("Ecart", "K")
    assert derived in ctrl.graph_ctrl.curves
    (analysis,) = nodes(ch1.analyses)
    assert analysis.display_name == "Ecart = [CH1] - [CH2]"


def test_identifier_channel_number_and_scientific_notation(ctrl, files):
    ch1, ch2 = files[0].signals
    formula(ctrl, ch1, "CH2*1e-3 + 4.18e3")
    np.testing.assert_allclose(result(ch1).y, ch2.y * 1e-3 + 4180)


def test_constant_formula_fills_time_base(ctrl, files):
    ch1 = files[0].signals[0]
    formula(ctrl, ch1, "max([CH1])")
    np.testing.assert_allclose(result(ch1).y, np.full(ch1.x.size, ch1.y.max()))


def test_time_function_on_host_samples_aliases(ctrl, files):
    """50 Hz sur les échantillons à 1 s du fichier : tous les points sur des zéros."""
    ch1 = files[0].signals[0]
    formula(ctrl, ch1, "100*sin(2*pi*50*time)")
    np.testing.assert_allclose(result(ch1).y, 0, atol=1e-6)


def test_time_function_with_own_period(ctrl, files):
    ch1 = files[0].signals[0]
    formula(ctrl, ch1, "100*sin(2*pi*50*time)", time_base="Own period", period=0.001)
    derived = result(ch1)
    assert derived.x.size == 599_001
    assert derived.x[0] == ch1.x[0] and derived.x[-1] == pytest.approx(ch1.x[-1])
    assert derived.y.max() == pytest.approx(100, rel=1e-3)


def test_too_many_points_refused(ctrl, files, warnings_shown):
    ch1 = files[0].signals[0]
    assert not formula(ctrl, ch1, "time", time_base="Own period", period=1e-6)
    assert "Own period too small" in str(warnings_shown[0])


def test_channel_of_other_file_interpolated(ctrl, files):
    a, b = files
    b.set_params({"label": "200 W", "offset": 100})          # fileB décalé de 100 s
    formula(ctrl, a.signals[0], "[200 W:CH1] - [CH1]")
    y = result(a.signals[0]).y
    assert np.isnan(y[:100]).all()                           # hors de la zone commune
    expected = np.interp(a.signals[0].x[100:], b.signals[0].x, b.signals[0].y) \
        - a.signals[0].y[100:]
    np.testing.assert_allclose(y[100:], expected)


def test_other_file_by_file_name_and_case(ctrl, files):
    a, b = files
    formula(ctrl, a.signals[0], "[FILEB:ch1]")              # nom du fichier, casse ignorée
    np.testing.assert_allclose(result(a.signals[0]).y, b.signals[0].y)


def test_slower_sampling_warning(ctrl, files, tmp_path):
    path = tmp_path / "lent.csv"
    _write_xy_csv(path, 120, np.arange(120.0), np.ones(120))
    ctrl.import_ctrl.opts["default_sampling_csv"] = 5        # une valeur toutes les 5 s
    load(ctrl, str(path).replace("\\", "/"))
    ok, message = ctrl.check_formula(files[0].signals[0], {"formula": "[lent:CH1]"})
    assert ok and "plus lent" in message


@pytest.mark.parametrize("text, error", [("[T AMB]", "Unknown channel [T AMB]"),
                                         ("[autre:CH1]", "Unknown file 'autre'"),
                                         ("CH1 +", "Invalid syntax"),
                                         ("[CH1", "Missing ']'")])
def test_errors_reported_nothing_added(ctrl, files, warnings_shown, text, error):
    ch1 = files[0].signals[0]
    assert not formula(ctrl, ch1, text)
    assert error in str(warnings_shown[0])
    assert nodes(ch1.analyses) == []
    assert ctrl.workspace_ctrl.undo_stack.count() == 0


def test_recomputed_when_input_changes(ctrl, files):
    ch1, ch2 = files[0].signals
    formula(ctrl, ch1, "[CH2]*2")
    ctrl.workspace_ctrl.push(ch2, add(T.OFFSET, {"offset": 10.0}))
    np.testing.assert_allclose(result(ch1).y, (ch2.raw_y + 10) * 2)
    ctrl.workspace_ctrl.undo_stack.undo()
    np.testing.assert_allclose(result(ch1).y, ch2.raw_y * 2)


def test_removed_file_then_undo(ctrl, files, monkeypatch):
    monkeypatch.setattr(QtWidgets.QMessageBox, "question",
                        lambda *a, **k: QtWidgets.QMessageBox.StandardButton.Yes)
    a, b = files
    formula(ctrl, a.signals[0], "[fileB:CH2]")
    ctrl.remove_file(b, confirm=False)
    (analysis,) = nodes(a.signals[0].analyses)
    assert analysis.error is not None
    assert not [d for d in a.signals[0].derived_signals if d.metadata.get("type") == "formula"]
    ctrl.workspace_ctrl.undo_stack.undo()
    np.testing.assert_allclose(result(a.signals[0]).y, b.signals[1].y)


def test_modify_formula_and_undo(ctrl, files):
    ch1, ch2 = files[0].signals
    formula(ctrl, ch1, "[CH2]")
    ctrl.workspace_ctrl.push(ch1, make_request(M.MODIFY_ACTION, T.FORMULA,
                                               {"formula": "[CH2]+1"}, 0))
    np.testing.assert_allclose(result(ch1).y, ch2.y + 1)
    ctrl.workspace_ctrl.undo_stack.undo()
    np.testing.assert_allclose(result(ch1).y, ch2.y)


def test_project_reload(ctrl, files, tmp_path):
    a, b = files
    b.set_params({"label": "200 W"})
    formula(ctrl, a.signals[0], "[200 W:CH1]-[CH1]", name="Delta", unit="K")
    project = tmp_path / "project.json"
    ctrl.workspace.save(project)
    ctrl.import_ctrl.openProject(str(project))
    a, b = ctrl.workspace.files
    derived = result(a.signals[0])
    assert (derived.name, derived.unit) == ("Delta", "K")
    np.testing.assert_allclose(derived.y, b.signals[0].y - a.signals[0].y)


def test_menu_action_with_dialog(ctrl, files, monkeypatch):
    ch1 = files[0].signals[0]
    ctrl.view.treefile.setCurrentIndex(ctrl.model.signal_index(ch1))
    monkeypatch.setattr(ctrl, "_ask_formula",
                        lambda sig, defaults=None: {"formula": "[CH1]*2", "name": "x2",
                                                    "unit": "", "time_base": "Host file",
                                                    "period": 0.001})
    ctrl._action_concentrator(M.ADD_ACTION, T.FORMULA)
    np.testing.assert_allclose(result(ch1).y, ch1.y * 2)
    # paramètres affichés dans le ParameterTree à la sélection de l'analyse
    assert ctrl.param_ctrl.param.child("Formula").value() == "[CH1]*2"


def test_cancelled_dialog_adds_nothing(ctrl, files, monkeypatch):
    ch1 = files[0].signals[0]
    ctrl.view.treefile.setCurrentIndex(ctrl.model.signal_index(ch1))
    monkeypatch.setattr(ctrl, "_ask_formula", lambda sig, defaults=None: None)
    ctrl._action_concentrator(M.ADD_ACTION, T.FORMULA)
    assert nodes(ch1.analyses) == []


def test_formula_channels_list(ctrl, files):
    files[1].set_params({"label": "200 W"})
    assert ctrl.formula_channels(files[0].signals[0]) == \
           ["[CH1]", "[CH2]", "time", "[200 W:CH1]", "[200 W:CH2]"]


def test_dialog_checks_and_inserts(ctrl, files):
    from ressources.custom_dialogs import FormulaDialog
    sig = files[0].signals[0]
    dialog = FormulaDialog(ctrl.formula_channels(sig),
                           lambda params: ctrl.check_formula(sig, params))
    ok_button = dialog.buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok)
    assert not ok_button.isEnabled() and "Saisissez" in dialog.message.text()
    dialog._insert("[CH2]")
    dialog.formula.insert("*2")
    assert ok_button.isEnabled() and "600 points" in dialog.message.text()
    dialog.formula.setText("[nope]")
    assert not ok_button.isEnabled() and "Unknown channel" in dialog.message.text()
    assert not dialog.period.isEnabled()
    dialog.time_base.setCurrentText("Own period")
    assert dialog.period.isEnabled()
