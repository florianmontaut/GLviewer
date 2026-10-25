# tests/conftest.py
"""
Fixtures communes : application Qt sans fenêtre (offscreen), profil utilisateur
temporaire (pour ne pas toucher ~/MVC_test/settings.json) et fichiers CSV de test.
"""

import os
import sys
import pathlib
import tempfile
import traceback

# À faire AVANT tout import Qt / du projet
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_FAKE_HOME = tempfile.mkdtemp(prefix="glviewer_home_")
os.environ["USERPROFILE"] = _FAKE_HOME
os.environ["HOME"] = _FAKE_HOME

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np
import pytest
from PyQt6 import QtWidgets


@pytest.fixture(scope="session")
def qapp():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    yield app


@pytest.fixture
def qt_errors(monkeypatch):
    """
    PyQt n'interrompt pas l'exécution quand une exception Python est levée dans
    un slot ou une méthode virtuelle (ex: QUndoCommand.redo) : elle est juste
    passée à sys.excepthook. On la collecte pour faire échouer le test.
    """
    errors = []
    monkeypatch.setattr(sys, "excepthook", lambda *exc: errors.append(exc))
    yield errors
    assert not errors, "Exception levée dans un slot Qt :\n" + "".join(
        traceback.format_exception(*errors[0]))


@pytest.fixture
def warnings_shown(monkeypatch):
    """Remplace les QMessageBox.warning (bloquants) par un enregistrement."""
    shown = []
    monkeypatch.setattr(QtWidgets.QMessageBox, "warning",
                        lambda *args, **kw: shown.append(args))
    return shown


@pytest.fixture
def dialogs_opened(monkeypatch):
    """
    Un QDialog.exec() modal bloquerait le test indéfiniment (offscreen, personne
    pour cliquer) : on le referme aussitôt (Rejected) et on l'enregistre.
    """
    opened = []
    def fake_exec(self):
        opened.append(type(self).__name__)
        return QtWidgets.QDialog.DialogCode.Rejected
    monkeypatch.setattr(QtWidgets.QDialog, "exec", fake_exec)
    return opened


@pytest.fixture
def ctrl(qapp, qt_errors, warnings_shown, dialogs_opened, tmp_path, monkeypatch):
    # profil vierge par test : settings.json / fichiers récents isolés
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("HOME", str(home))

    from view.main_window import MainWindow
    from controller.main_controller import MainController
    from ressources import custom_viewer_settings

    window = MainWindow()
    controller = MainController(window, custom_viewer_settings.params)
    # travail non enregistré (ouverture d'un projet, fermeture) : abandonné sans question
    # (boîte bloquante) ; tests/test_save_project.py remplace cette réponse
    monkeypatch.setattr(controller, "_ask_unsaved_changes", lambda: "discard")
    yield controller
    window.close()


def _write_xy_csv(path, n, y1, y2):
    """Format CSV générique (paires X;Y) attendu par ImportController.openCsvFiles."""
    with open(path, "w") as f:
        f.write("Time;CH1;;CH2;\n")
        for i in range(n):
            f.write(f"{i};{y1[i]:.4f};{i};{y2[i]:.4f};\n")


@pytest.fixture
def csv_files(tmp_path):
    """Deux fichiers : CH1 = échelon thermique (1er ordre), CH2 = sinus."""
    n = 600
    t = np.arange(n)
    rng = np.random.default_rng(0)
    paths = []
    for name in ("fileA", "fileB"):
        step = 25 + 20 * (1 - np.exp(-t / 80)) + rng.normal(0, 0.05, n)
        sine = 20 + np.sin(t / 20)
        p = tmp_path / f"{name}.csv"
        _write_xy_csv(p, n, step, sine)
        # QFileDialog renvoie des chemins avec des '/'
        paths.append(str(p).replace("\\", "/"))
    return paths
