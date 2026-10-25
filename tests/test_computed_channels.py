# tests/test_computed_channels.py
"""
Voies calculées : voie d'un fichier donnée par une formule ([T AMB], [200 W:T AMB], CH3,
time), base de temps du fichier hôte ou période propre ; filtres et analyses comme une
voie mesurée, recalcul, annulation, sauvegarde.
"""
import json

import numpy as np
import pytest
from PyQt6 import QtCore, QtWidgets

from conftest import _write_xy_csv
from ressources.custom_types import qSignalType as T, ActionModifier as M
from helpers import add, load, nodes

Qt = QtCore.Qt


@pytest.fixture
def files(ctrl, csv_files):
    return list(load(ctrl, *csv_files))          # fileA, fileB : CH1 échelon, CH2 sinus


@pytest.fixture
def dialog(ctrl, monkeypatch):
    """Réponse de la boîte « Add a computed channel » (None : annulée) et valeurs reçues."""
    state = {"answer": None, "defaults": None}

    def ask(file_obj, defaults=None):
        state["defaults"] = dict(defaults or {})
        answer = state["answer"]
        return None if answer is None else {**state["defaults"], **answer}
    monkeypatch.setattr(ctrl, "_ask_formula", ask)
    return state


def channel(ctrl, dialog, file_obj, formula, **params):
    """Ajoute une voie calculée au fichier, comme depuis le menu ; la retourne."""
    dialog["answer"] = {"formula": formula, **params}
    before = list(file_obj.signals)
    ctrl.add_computed_channel(file_obj)
    added = [s for s in file_obj.signals if s not in before]
    return added[0] if added else None


def _select(ctrl, obj):
    item = ctrl.model.find_item(ctrl.model.root, obj)
    ctrl.view.treefile.setCurrentIndex(ctrl.model.index_from_item(item))


def _undo(ctrl):
    ctrl.workspace_ctrl.undo_stack.undo()


# ---------------- création ----------------

def test_channel_added_to_file_tree_graph_and_channel_view(ctrl, files, dialog):
    a = files[0]
    sig = channel(ctrl, dialog, a, "[CH1] - [CH2]", name="Ecart", unit="K")
    ch1, ch2 = a.signals[:2]
    assert a.signals[-1] is sig and sig.is_computed
    np.testing.assert_allclose(sig.x, ch1.x)
    np.testing.assert_allclose(sig.y, ch1.y - ch2.y)
    assert sig.unit == "K"
    assert ctrl.model.data(ctrl.model.signal_index(sig), Qt.ItemDataRole.DisplayRole) == "ƒ Ecart"
    assert "Ecart = [CH1] - [CH2]" in ctrl.model.data(ctrl.model.signal_index(sig),
                                                       Qt.ItemDataRole.ToolTipRole)
    assert sig in ctrl.graph_ctrl.curves
    assert ctrl.channel_model.signal_index(sig).isValid()

    _undo(ctrl)
    assert sig not in a.signals and sig not in ctrl.graph_ctrl.curves
    assert not ctrl.model.signal_index(sig).isValid()
    ctrl.workspace_ctrl.undo_stack.redo()
    assert a.signals[-1] is sig and sig in ctrl.graph_ctrl.curves


def test_from_file_item_without_prefill(ctrl, files, dialog):
    _select(ctrl, files[0])
    ctrl._action_concentrator(M.ADD_ACTION, T.FORMULA)
    assert dialog["defaults"] == {"formula": "", "name": "Formula"}


def test_from_channel_prefilled(ctrl, files, dialog):
    ctrl.view.treefile.setCurrentIndex(ctrl.model.signal_index(files[0].signals[1]))
    ctrl._action_concentrator(M.ADD_ACTION, T.FORMULA)
    assert dialog["defaults"] == {"formula": "[CH2]", "name": "Formula"}


def test_menu_enabled_on_file_item(ctrl, files):
    _select(ctrl, files[0])
    action = ctrl.tree_ctrl.menu._actions[T.FORMULA]
    assert action.isEnabled() and action.text() == "Add a computed channel"


def test_default_names_are_free(ctrl, files, dialog):
    a = files[0]
    channel(ctrl, dialog, a, "1")
    _select(ctrl, a)
    dialog["answer"] = None
    ctrl.add_computed_channel(a)
    assert dialog["defaults"]["name"] == "Formula 2"


def test_cancelled_dialog_adds_nothing(ctrl, files, dialog):
    dialog["answer"] = None
    ctrl.add_computed_channel(files[0])
    assert len(files[0].signals) == 2 and ctrl.workspace_ctrl.undo_stack.count() == 0


@pytest.mark.parametrize("formula, error", [("[T AMB]", "Unknown channel [T AMB]"),
                                            ("[autre:CH1]", "Unknown file 'autre'"),
                                            ("CH1 +", "Invalid syntax")])
def test_invalid_formula_refused(ctrl, files, dialog, warnings_shown, formula, error):
    ok, message = ctrl.check_formula(files[0], {"formula": formula})
    assert not ok and error in message


def test_existing_name_refused(ctrl, files, warnings_shown, dialog):
    assert channel(ctrl, dialog, files[0], "1", name="CH2") is None
    assert "already exists" in str(warnings_shown[0])


# ---------------- formules ----------------

def test_channel_number_scientific_constant(ctrl, files, dialog):
    a = files[0]
    s1 = channel(ctrl, dialog, a, "CH2*1e-3 + 4.18e3", name="a")
    np.testing.assert_allclose(s1.y, a.signals[1].y * 1e-3 + 4180)
    s2 = channel(ctrl, dialog, a, "max([CH1])", name="b")
    np.testing.assert_allclose(s2.y, np.full(a.signals[0].x.size, a.signals[0].y.max()))


def test_time_function_on_host_samples_aliases(ctrl, files, dialog):
    """50 Hz sur les échantillons à 1 s du fichier : tous les points sur des zéros."""
    sig = channel(ctrl, dialog, files[0], "100*sin(2*pi*50*time)")
    np.testing.assert_allclose(sig.y, 0, atol=1e-6)


def test_time_function_with_own_period(ctrl, files, dialog):
    sig = channel(ctrl, dialog, files[0], "100*sin(2*pi*50*time)", time_base="Own period",
                  period=0.001)
    assert sig.x.size == 599_001
    assert sig.y.max() == pytest.approx(100, rel=1e-3)


def test_too_many_points_refused(ctrl, files):
    ok, message = ctrl.check_formula(files[0], {"formula": "time", "time_base": "Own period",
                                                "period": 1e-6})
    assert not ok and "Own period too small" in message


def test_channel_of_other_file_interpolated(ctrl, files, dialog):
    a, b = files
    b.set_params({"label": "200 W", "offset": 100})          # fileB décalé de 100 s
    sig = channel(ctrl, dialog, a, "[200 W:CH1] - [CH1]")
    assert np.isnan(sig.y[:100]).all()                       # hors de la zone commune
    expected = np.interp(a.signals[0].x[100:], b.signals[0].x, b.signals[0].y) \
        - a.signals[0].y[100:]
    np.testing.assert_allclose(sig.y[100:], expected)


def test_other_file_by_name_and_case(ctrl, files, dialog):
    sig = channel(ctrl, dialog, files[0], "[FILEB:ch1]")
    np.testing.assert_allclose(sig.y, files[1].signals[0].y)


def test_slower_sampling_warning(ctrl, files, tmp_path):
    path = tmp_path / "lent.csv"
    _write_xy_csv(path, 120, np.arange(120.0), np.ones(120))
    ctrl.import_ctrl.opts["default_sampling_csv"] = 5        # une valeur toutes les 5 s
    load(ctrl, str(path).replace("\\", "/"))
    ok, message = ctrl.check_formula(files[0], {"formula": "[lent:CH1]"})
    assert ok and "plus lent" in message


def test_uses_filtered_channels(ctrl, files, dialog):
    ch2 = files[0].signals[1]
    ctrl.workspace_ctrl.push(ch2, add(T.OFFSET, {"offset": 5.0}))
    sig = channel(ctrl, dialog, files[0], "[CH2]")
    np.testing.assert_allclose(sig.y, ch2.raw_y + 5)


# ---------------- comme une voie mesurée ----------------

def test_filters_and_analyses_on_computed_channel(ctrl, files, dialog):
    sig = channel(ctrl, dialog, files[0], "[CH1]*2", name="Pertes")
    ctrl.workspace_ctrl.push(sig, add(T.OFFSET, {"offset": 1.0}))
    np.testing.assert_allclose(sig.y, files[0].signals[0].y * 2 + 1)
    assert ctrl.model.data(ctrl.model.signal_index(sig), Qt.ItemDataRole.DisplayRole) == "ƒ Pertes"
    ctrl.workspace_ctrl.push(sig, add(T.MODEL, {"model_range": [0.0, 599.0]}))
    (model,) = nodes(sig.analyses)
    assert model.results.T_inf == pytest.approx(90, rel=0.02)   # 2 × 45 °C


def test_grouped_in_channel_view(ctrl, files, dialog):
    for file_obj in files:
        channel(ctrl, dialog, file_obj, "[CH1]-[CH2]", name="Pertes")
    groups = {g.name: len(g.signals) for g in ctrl.channel_model.groups()}
    assert groups["Pertes"] == 2


def test_computed_from_computed(ctrl, files, dialog):
    a = files[0]
    channel(ctrl, dialog, a, "[CH1]*2", name="Double")
    quad = channel(ctrl, dialog, a, "[Double]*2", name="Quadruple")
    np.testing.assert_allclose(quad.y, a.signals[0].y * 4)


# ---------------- recalcul ----------------

def test_recomputed_and_redrawn_when_input_changes(ctrl, files, dialog):
    ch2 = files[0].signals[1]
    sig = channel(ctrl, dialog, files[0], "[CH2]*2")
    ctrl.workspace_ctrl.push(ch2, add(T.OFFSET, {"offset": 10.0}))
    np.testing.assert_allclose(sig.y, (ch2.raw_y + 10) * 2)
    _, y = ctrl.graph_ctrl.curves[sig].getOriginalDataset()
    np.testing.assert_allclose(y, (ch2.raw_y + 10) * 2)
    _undo(ctrl)
    np.testing.assert_allclose(sig.y, ch2.raw_y * 2)


def test_follows_file_offset(ctrl, files, dialog):
    sig = channel(ctrl, dialog, files[0], "[CH1]")
    files[0].set_params({"offset": 50})
    np.testing.assert_allclose(sig.x, files[0].signals[0].x)


def test_removed_file_then_undo(ctrl, files, dialog):
    a, b = files
    sig = channel(ctrl, dialog, a, "[fileB:CH2]")
    ctrl.remove_file(b, confirm=False)
    assert np.isnan(sig.y).all() and sig.error
    assert ctrl.model.data(ctrl.model.signal_index(sig), Qt.ItemDataRole.DisplayRole).endswith("⚠")
    _undo(ctrl)
    np.testing.assert_allclose(sig.y, b.signals[1].y)
    assert sig.error is None


# ---------------- modification (ParameterTree) ----------------

def test_modify_formula_from_parameter_tree_and_undo(ctrl, files, dialog, qapp):
    a = files[0]
    sig = channel(ctrl, dialog, a, "[CH2]")
    _select(ctrl, sig)
    ctrl.param_ctrl.param.child("Formula").setValue("[CH2]+1")
    qapp.processEvents()
    np.testing.assert_allclose(sig.y, a.signals[1].y + 1)
    _, y = ctrl.graph_ctrl.curves[sig].getOriginalDataset()
    np.testing.assert_allclose(y, a.signals[1].y + 1)
    _undo(ctrl)
    assert sig.formula == "[CH2]"
    np.testing.assert_allclose(sig.y, a.signals[1].y)


def test_invalid_modification_refused(ctrl, files, dialog, warnings_shown, qapp):
    sig = channel(ctrl, dialog, files[0], "[CH2]")
    _select(ctrl, sig)
    ctrl.param_ctrl.param.child("Formula").setValue("[nope]")
    qapp.processEvents()
    assert sig.formula == "[CH2]"
    assert "Unknown channel" in str(warnings_shown[0])
    assert ctrl.param_ctrl.param.child("Formula").value() == "[CH2]"   # valeur remise


def test_circular_reference_refused(ctrl, files, dialog, warnings_shown, qapp):
    a = files[0]
    first = channel(ctrl, dialog, a, "[CH1]", name="A")
    channel(ctrl, dialog, a, "[A]*2", name="B")
    _select(ctrl, first)
    ctrl.param_ctrl.param.child("Formula").setValue("[B]")
    qapp.processEvents()
    assert first.formula == "[CH1]"
    assert "Circular reference" in str(warnings_shown[0])


def test_rename_keeps_name_check(ctrl, files, dialog, warnings_shown, qapp):
    sig = channel(ctrl, dialog, files[0], "[CH2]", name="X")
    _select(ctrl, sig)
    ctrl.param_ctrl.param.child("Curve name").setValue("CH1")
    qapp.processEvents()
    assert sig.name == "X" and "already exists" in str(warnings_shown[0])
    ctrl.param_ctrl.param.child("Curve name").setValue("Pertes")
    qapp.processEvents()
    assert sig.name == "Pertes"
    assert ctrl.model.data(ctrl.model.signal_index(sig), Qt.ItemDataRole.DisplayRole) == "ƒ Pertes"


# ---------------- suppression ----------------

def test_delete_and_undo(ctrl, files, dialog):
    a = files[0]
    first = channel(ctrl, dialog, a, "1", name="A")
    channel(ctrl, dialog, a, "2", name="B")
    _select(ctrl, first)
    ctrl._action_concentrator(M.ADD_ACTION, T.DEL)
    assert first not in a.signals and first not in ctrl.graph_ctrl.curves
    _undo(ctrl)
    assert a.signals.index(first) == 2                       # remise à sa place
    assert ctrl.model.signal_index(first).isValid()


def test_measured_channel_not_deletable(ctrl, files):
    ctrl.view.treefile.setCurrentIndex(ctrl.model.signal_index(files[0].signals[0]))
    ctrl._action_concentrator(M.ADD_ACTION, T.DEL)
    assert len(files[0].signals) == 2


# ---------------- sauvegarde ----------------

def test_project_reload(ctrl, files, dialog, tmp_path):
    a, b = files
    b.set_params({"label": "200 W"})
    sig = channel(ctrl, dialog, a, "[200 W:CH1]-[CH1]", name="Delta", unit="K")
    ctrl.workspace_ctrl.push(sig, add(T.OFFSET, {"offset": 1.0}))
    project = tmp_path / "project.json"
    ctrl.workspace.save(project)
    ctrl.import_ctrl.openProject(str(project))
    a, b = ctrl.workspace.files
    sig = a.signals[-1]
    assert sig.is_computed and (sig.name, sig.unit) == ("Delta", "K")
    np.testing.assert_allclose(sig.y, b.signals[0].y - a.signals[0].y + 1)
    assert sig in ctrl.graph_ctrl.curves


def test_old_formula_analysis_converted(ctrl, files, tmp_path):
    project = tmp_path / "old.json"
    ctrl.workspace.save(project)
    data = json.loads(project.read_text(encoding="utf-8"))
    data["workspace"]["files"][0]["signals"][0]["analyses"].append(
        ["abc", {"type": "FORMULA", "params": {"formula": "[CH1]*2", "name": "x2",
                                               "unit": "", "time_base": "Host file",
                                               "period": 0.001}}])
    project.write_text(json.dumps(data), encoding="utf-8")
    ctrl.import_ctrl.openProject(str(project))
    a = ctrl.workspace.files[0]
    assert nodes(a.signals[0].analyses) == []
    sig = a.signals[-1]
    assert sig.is_computed and sig.name == "x2"
    np.testing.assert_allclose(sig.y, a.signals[0].y * 2)


# ---------------- boîte de saisie ----------------

def test_formula_channels_list(ctrl, files):
    files[1].set_params({"label": "200 W"})
    assert ctrl.formula_channels(files[0]) == \
           ["[CH1]", "[CH2]", "time", "[200 W:CH1]", "[200 W:CH2]"]


def test_dialog_checks_and_inserts(ctrl, files):
    from ressources.custom_dialogs import FormulaDialog
    a = files[0]
    dialog = FormulaDialog(ctrl.formula_channels(a),
                           lambda params: ctrl.check_formula(a, params), {"formula": "[CH1]"})
    ok_button = dialog.buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok)
    assert not dialog.formula.hasSelectedText()
    dialog.formula.insert("*2")
    assert dialog.formula.text() == "[CH1]*2"
    assert ok_button.isEnabled() and "600 points" in dialog.message.text()
    dialog.formula.setText("")
    assert not ok_button.isEnabled() and "Saisissez" in dialog.message.text()
    dialog._insert("[nope]")
    assert not ok_button.isEnabled() and "Unknown channel" in dialog.message.text()
    assert not dialog.period.isEnabled()
    dialog.time_base.setCurrentText("Own period")
    assert dialog.period.isEnabled()
