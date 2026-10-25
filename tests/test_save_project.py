# tests/test_save_project.py
"""
Enregistrement du projet ouvert (Files > Save, Ctrl+S), travail non enregistré signalé
(« * » dans le titre) et proposé à l'enregistrement avant de fermer le logiciel ou
d'ouvrir un autre projet.
"""
import json

import pytest
from PyQt6 import QtCore, QtWidgets

from ressources.custom_types import qSignalType as T
from helpers import add, load


@pytest.fixture
def answers(ctrl, monkeypatch):
    """Réponses à « Enregistrer les modifications ? » (save / discard / cancel)."""
    state = {"answer": "cancel", "asked": 0}

    def ask():
        state["asked"] += 1
        return state["answer"]
    monkeypatch.setattr(ctrl, "_ask_unsaved_changes", ask)
    return state


@pytest.fixture
def save_as(monkeypatch):
    """Chemin choisi dans « Save Workspace » ("" : annulé) et nombre d'ouvertures."""
    state = {"path": "", "opened": 0}

    def dialog(*args, **kwargs):
        state["opened"] += 1
        return state["path"], "Workspace (*.json)"
    monkeypatch.setattr(QtWidgets.QFileDialog, "getSaveFileName", dialog)
    return state


@pytest.fixture
def project(ctrl, csv_files, tmp_path):
    """Projet enregistré puis rouvert : deux fichiers, aucune modification."""
    load(ctrl, *csv_files)
    path = str(tmp_path / "essais.json").replace("\\", "/")
    ctrl.workspace.save(path)
    ctrl.import_ctrl.openProject(path)
    return path


def _modify(ctrl):
    sig = ctrl.workspace.files[0].signals[0]
    ctrl.workspace_ctrl.push(sig, add(T.OFFSET, {"offset": 1.0}))
    return sig


# ---------------- modifications détectées ----------------

def test_new_session_not_modified(ctrl):
    assert not ctrl.is_modified() and ctrl.view.windowTitle() == "GLViewer"


def test_loaded_files_are_not_modifications(ctrl, csv_files):
    load(ctrl, *csv_files)
    assert not ctrl.is_modified()
    _modify(ctrl)
    assert ctrl.is_modified()
    assert ctrl.view.windowTitle() == "GLViewer — projet non enregistré *"


def test_opened_project_title_and_star(ctrl, project):
    assert ctrl.view.windowTitle() == "GLViewer — essais.json"
    _modify(ctrl)
    assert ctrl.view.windowTitle() == "GLViewer — essais.json *"


def test_undo_back_to_saved_state(ctrl, project):
    _modify(ctrl)
    ctrl.workspace_ctrl.undo_stack.undo()
    assert not ctrl.is_modified()
    assert ctrl.view.windowTitle() == "GLViewer — essais.json"


def test_visibility_and_label_are_modifications(ctrl, project, qapp):
    sig = ctrl.workspace.files[0].signals[1]
    ctrl.channel_model.setData(ctrl.channel_model.signal_index(sig), 0,      # décochée
                               QtCore.Qt.ItemDataRole.CheckStateRole)
    assert ctrl.is_modified() and ctrl.view.windowTitle().endswith("*")


def test_file_label_is_modification(ctrl, project, qapp):
    file_obj = ctrl.workspace.files[1]
    item = ctrl.model.find_item(ctrl.model.root, file_obj)
    ctrl.view.treefile.setCurrentIndex(ctrl.model.index_from_item(item))
    ctrl.param_ctrl.param.child("Label").setValue("200 W")
    qapp.processEvents()
    assert ctrl.is_modified() and ctrl.view.windowTitle().endswith("*")


# ---------------- Save / Save as ----------------

def test_save_writes_opened_project_without_dialog(ctrl, project, save_as):
    sig = _modify(ctrl)
    ctrl.view.actionSave.trigger()
    assert save_as["opened"] == 0
    assert not ctrl.is_modified()
    assert ctrl.view.windowTitle() == "GLViewer — essais.json"
    data = json.loads(open(project, encoding="utf-8").read())
    saved = data["workspace"]["files"][0]["signals"][0]["pipeline"]
    assert [node["type"] for _, node in saved] == ["OFFSET"]


def test_save_without_project_asks_for_a_file(ctrl, csv_files, save_as, tmp_path):
    load(ctrl, *csv_files)
    _modify(ctrl)
    save_as["path"] = str(tmp_path / "nouveau.json").replace("\\", "/")
    ctrl.view.actionSave.trigger()
    assert save_as["opened"] == 1 and ctrl.workspace.path == save_as["path"]
    assert not ctrl.is_modified()
    ctrl.view.actionSave.trigger()                 # ensuite : même fichier, sans boîte
    assert save_as["opened"] == 1


def test_save_as_keeps_star_if_cancelled(ctrl, project, save_as):
    _modify(ctrl)
    ctrl.view.actionSave_to.trigger()
    assert save_as["opened"] == 1 and ctrl.is_modified()


def test_shortcuts(ctrl):
    assert ctrl.view.actionSave.shortcut().toString() == "Ctrl+S"
    assert ctrl.view.actionSave_to.text() == "Save as..."


# ---------------- fermeture ----------------

def test_close_without_changes_asks_nothing(ctrl, project, answers):
    ctrl.view.show()
    assert ctrl.view.close()
    assert answers["asked"] == 0


def test_close_cancelled(ctrl, project, answers):
    ctrl.view.show()
    _modify(ctrl)
    answers["answer"] = "cancel"
    assert not ctrl.view.close()
    assert ctrl.view.isVisible() and answers["asked"] == 1


def test_close_discard(ctrl, project, answers):
    ctrl.view.show()
    _modify(ctrl)
    answers["answer"] = "discard"
    ctrl.view.actionQuit.trigger()
    assert not ctrl.view.isVisible()
    data = json.loads(open(project, encoding="utf-8").read())
    assert data["workspace"]["files"][0]["signals"][0]["pipeline"] == []


def test_close_save(ctrl, project, answers, save_as):
    ctrl.view.show()
    _modify(ctrl)
    answers["answer"] = "save"
    assert ctrl.view.close()
    data = json.loads(open(project, encoding="utf-8").read())
    assert len(data["workspace"]["files"][0]["signals"][0]["pipeline"]) == 1
    assert save_as["opened"] == 0


def test_close_save_cancelled_keeps_window(ctrl, csv_files, answers, save_as):
    ctrl.view.show()
    load(ctrl, *csv_files)
    _modify(ctrl)
    answers["answer"] = "save"                     # pas de projet : boîte annulée
    assert not ctrl.view.close()
    assert ctrl.view.isVisible() and save_as["opened"] == 1


# ---------------- ouverture d'un autre projet ----------------

def test_open_other_project_cancelled(ctrl, project, answers, tmp_path):
    sig = _modify(ctrl)
    other = str(tmp_path / "autre.json")
    ctrl.workspace.save(other)                      # change aussi le projet courant
    ctrl.workspace.path = project
    ctrl._mark_saved()
    ctrl.workspace_ctrl.push(sig, add(T.OFFSET, {"offset": 2.0}))
    workspace = ctrl.workspace
    answers["answer"] = "cancel"
    ctrl.import_ctrl.openProject(other)
    assert ctrl.workspace is workspace and ctrl.is_modified()


def test_open_other_project_after_save(ctrl, project, answers, tmp_path):
    _modify(ctrl)
    answers["answer"] = "save"
    other = tmp_path / "autre.json"
    other.write_text(open(project, encoding="utf-8").read(), encoding="utf-8")
    ctrl.import_ctrl.openProject(str(other))
    data = json.loads(open(project, encoding="utf-8").read())
    assert len(data["workspace"]["files"][0]["signals"][0]["pipeline"]) == 1
    assert ctrl.workspace.path == str(other) and not ctrl.is_modified()
