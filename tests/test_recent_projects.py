# tests/test_recent_projects.py
"""Menu Files > Recent files : les projets .json y figurent et s'y rouvrent."""
import json

import pytest
from PyQt6 import QtWidgets

from helpers import load


@pytest.fixture
def save_as(monkeypatch):
    """Chemin choisi dans la boîte « Save Workspace » ("" : annulé)."""
    choice = {"path": ""}
    monkeypatch.setattr(QtWidgets.QFileDialog, "getSaveFileName",
                        lambda *a, **k: (choice["path"], "Workspace (*.json)"))
    return choice


def _recent(ctrl):
    return [a.text() for a in ctrl.view.recent_files_menu.actions()]


def _entries(ctrl):
    with open(ctrl.menu_ctrl.user_config) as f:
        return json.load(f)["files"]


def test_saved_project_in_recent_files(ctrl, csv_files, save_as, tmp_path):
    load(ctrl, *csv_files)
    save_as["path"] = str(tmp_path / "essais.json").replace("\\", "/")
    ctrl.view.actionSave_to.trigger()

    assert _recent(ctrl)[0] == save_as["path"]
    assert _entries(ctrl)[0] == {"file_type": "JSON", "address": save_as["path"],
                                 "import_params": {}}
    assert ctrl.workspace.path == save_as["path"]


def test_cancelled_save_adds_nothing(ctrl, csv_files, save_as):
    load(ctrl, *csv_files)
    before = _recent(ctrl)
    ctrl.view.actionSave_to.trigger()
    assert _recent(ctrl) == before


def test_opened_project_in_recent_files_and_reopened(ctrl, csv_files, tmp_path):
    load(ctrl, *csv_files)
    project = str(tmp_path / "essais.json").replace("\\", "/")
    ctrl.workspace.save(project)
    ctrl.import_ctrl.openProject(project)
    assert _recent(ctrl)[0] == project
    # le projet n'ajoute pas ses fichiers un à un (ils étaient déjà dans la liste)
    assert _recent(ctrl).count(csv_files[0]) == 1

    # réouverture depuis le menu
    first_workspace = ctrl.workspace
    action = ctrl.view.recent_files_menu.actions()[0]
    action.trigger()
    assert ctrl.workspace is not first_workspace
    assert [f.name for f in ctrl.workspace.files] == ["fileA", "fileB"]
    assert ctrl.workspace.path == project
