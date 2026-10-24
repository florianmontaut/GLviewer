# tests/test_file_management.py
"""Retirer un fichier de l'espace de travail (annulable) et étiqueter un fichier."""
import json

import pytest
from PyQt6 import QtCore, QtWidgets

from ressources.custom_types import qSignalType as T, ActionModifier as M
from helpers import add, load, nodes


@pytest.fixture
def answer(monkeypatch):
    """Réponse à la confirmation « Retirer le fichier » (et texte affiché)."""
    state = {"button": QtWidgets.QMessageBox.StandardButton.Yes, "texts": []}

    def fake_question(parent, title, text, *args, **kw):
        state["texts"].append(text)
        return state["button"]
    monkeypatch.setattr(QtWidgets.QMessageBox, "question", fake_question)
    return state


@pytest.fixture
def two_files(ctrl, csv_files):
    # copie : load renvoie workspace.files, modifiée par la suppression
    return list(load(ctrl, *csv_files))


def _select(ctrl, obj):
    item = ctrl.model.find_item(ctrl.model.root, obj)
    ctrl.view.treefile.setCurrentIndex(ctrl.model.index_from_item(item))


def _delete(ctrl, obj):
    _select(ctrl, obj)
    ctrl._action_concentrator(M.ADD_ACTION, T.DEL)


def _file_rows(ctrl):
    return [child.obj for child in ctrl.model.root.children]


def _curves_of(ctrl, file_obj):
    return [s for s in ctrl.graph_ctrl.curves if getattr(s, "file", None) is file_obj]


# ---------------- retirer un fichier ----------------

def test_remove_file_after_confirmation(ctrl, two_files, answer):
    file_a, file_b = two_files
    ctrl.workspace_ctrl.push(file_a.signals[0], add(T.MODEL))
    count = ctrl.workspace_ctrl.undo_stack.count()

    _delete(ctrl, file_a)

    assert answer["texts"] and "annulable" in answer["texts"][0]
    assert ctrl.workspace.files == [file_b] and _file_rows(ctrl) == [file_b]
    assert _curves_of(ctrl, file_a) == []                  # voies et modèle
    assert ctrl.workspace_ctrl.undo_stack.count() == count + 1


def test_cancelled_confirmation_keeps_file(ctrl, two_files, answer):
    answer["button"] = QtWidgets.QMessageBox.StandardButton.No
    _delete(ctrl, two_files[0])
    assert ctrl.workspace.files == list(two_files)


def test_undo_restores_file_in_place(ctrl, two_files, answer):
    file_a, file_b = two_files
    sig = file_a.signals[0]
    ctrl.workspace_ctrl.push(sig, add(T.OFFSET, {"offset": 1.0}))
    ctrl.workspace_ctrl.push(sig, add(T.MODEL))
    derived = sig.derived_signals[0]
    _delete(ctrl, file_a)

    ctrl.workspace_ctrl.undo_stack.undo()

    assert ctrl.workspace.files == [file_a, file_b] and _file_rows(ctrl) == [file_a, file_b]
    assert [n.action_type for n in nodes(sig.pipeline)] == [T.OFFSET]
    assert sig.derived_signals == [derived]
    assert set(_curves_of(ctrl, file_a)) == set(file_a.signals) | {derived}
    sig_item = ctrl.model.find_signal_item(sig)
    assert [c.obj for c in sig_item.children] == nodes(sig.pipeline) + nodes(sig.analyses)

    ctrl.workspace_ctrl.undo_stack.redo()
    assert ctrl.workspace.files == [file_b] and _curves_of(ctrl, file_a) == []


def test_delete_key_in_tree(ctrl, two_files, answer):
    _select(ctrl, two_files[1])
    ctrl.tree_ctrl.delete_shortcut.activated.emit()
    assert ctrl.workspace.files == [two_files[0]]


def test_remove_clears_parameter_tree_and_cursor(ctrl, two_files, answer):
    file_a = two_files[0]
    ctrl.cursor_ctrl.set_signal(file_a.signals[0])
    _select(ctrl, file_a)
    assert ctrl.param_ctrl.param is not None

    ctrl._action_concentrator(M.ADD_ACTION, T.DEL)

    assert ctrl.cursor_ctrl.signal is None
    # après suppression, le premier fichier restant est sélectionné
    assert ctrl.param_ctrl.param.child("File name").value() == two_files[1].name


def test_saved_project_excludes_removed_file(ctrl, two_files, answer, tmp_path):
    _delete(ctrl, two_files[0])
    project = tmp_path / "project.json"
    ctrl.workspace.save(project)
    data = json.loads(project.read_text(encoding="utf-8"))
    assert [f["address"] for f in data["workspace"]["files"]] == [two_files[1].address]


def test_removed_file_can_be_loaded_again(ctrl, two_files, answer, csv_files):
    _delete(ctrl, two_files[0])
    load(ctrl, csv_files[0])
    assert [f.name for f in ctrl.workspace.files] == ["fileB", "fileA"]


# ---------------- dépendances ----------------

def test_dependent_diff_analysis_is_flagged(ctrl, two_files, answer):
    file_a, file_b = two_files
    sig_b = file_b.signals[0]
    ctrl.workspace_ctrl.push(sig_b, add(T.DIFF_EXT, {"reference": file_a.signals[0]}))
    analysis = nodes(sig_b.analyses)[0]

    _delete(ctrl, file_a)

    assert "1 analyse(s)" in answer["texts"][0]
    assert analysis.error and "retiré" in analysis.error and sig_b.derived_signals == []

    ctrl.workspace_ctrl.undo_stack.undo()
    assert analysis.error is None and len(sig_b.derived_signals) == 1


def test_reference_signal_cleared_and_restored(ctrl, two_files, answer):
    file_a = two_files[0]
    ref = file_a.signals[1]
    _select(ctrl, ref)
    ctrl._action_concentrator(M.ADD_ACTION, T.REF)
    assert ctrl.workspace.reference_signal is ref

    _delete(ctrl, file_a)
    assert ctrl.workspace.reference_signal is None and not ref.is_reference

    ctrl.workspace_ctrl.undo_stack.undo()
    assert ctrl.workspace.reference_signal is ref and ref.is_reference


# ---------------- supprimer un filtre / une analyse ----------------

def test_delete_filter_and_analysis_from_tree(ctrl, two_files):
    sig = two_files[0].signals[0]
    ctrl.workspace_ctrl.push(sig, add(T.OFFSET, {"offset": 1.0}))
    ctrl.workspace_ctrl.push(sig, add(T.MODEL))

    _delete(ctrl, nodes(sig.pipeline)[0])
    _delete(ctrl, nodes(sig.analyses)[0])

    assert len(sig.pipeline) == 0 and len(sig.analyses) == 0 and sig.derived_signals == []
    ctrl.workspace_ctrl.undo_stack.undo()
    ctrl.workspace_ctrl.undo_stack.undo()
    assert len(sig.pipeline) == 1 and len(sig.analyses) == 1


def _menu_enabled(ctrl, label="Delete selection"):
    return {a.text(): a.isEnabled() for a in ctrl.tree_ctrl.menu.menu.actions()}[label]


def test_delete_menu_enabled_only_for_deletable_items(ctrl, two_files):
    sig = two_files[0].signals[0]
    ctrl.workspace_ctrl.push(sig, add(T.OFFSET, {"offset": 1.0}))
    for obj, enabled in ((two_files[0], True), (sig, False), (nodes(sig.pipeline)[0], True)):
        _select(ctrl, obj)
        assert _menu_enabled(ctrl) is enabled


# ---------------- étiquette du fichier ----------------

def _set_label(ctrl, file_obj, label, qapp):
    _select(ctrl, file_obj)
    ctrl.param_ctrl.param.child("Label").setValue(label)
    qapp.processEvents()


def test_label_shown_in_tree(ctrl, two_files, qapp):
    file_a = two_files[0]
    _set_label(ctrl, file_a, "100 W / 55 °C", qapp)

    assert file_a.label == "100 W / 55 °C"
    index = ctrl.model.index_from_item(ctrl.model.find_item(ctrl.model.root, file_a))
    assert ctrl.model.data(index, QtCore.Qt.ItemDataRole.DisplayRole) == "fileA — 100 W / 55 °C"
    assert ctrl.model.data(index, QtCore.Qt.ItemDataRole.ToolTipRole) == file_a.address


def test_label_saved_in_project(ctrl, two_files, qapp, tmp_path):
    _set_label(ctrl, two_files[0], "100 W / 55 °C", qapp)
    project = tmp_path / "project.json"
    ctrl.workspace.save(project)

    ctrl.import_ctrl.openProject(str(project))

    assert [f.label for f in ctrl.workspace.files] == ["100 W / 55 °C", ""]
