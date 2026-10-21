# tests/test_import.py
import json
import os

import numpy as np

from helpers import load


def test_csv_import_with_overrange_check(ctrl, csv_files):
    # option par défaut de l'ImportController
    assert ctrl.import_ctrl.opts["remove_overrange"] is True
    files = load(ctrl, csv_files[0])

    assert [f.name for f in files] == ["fileA"]
    assert [s.name for s in files[0].signals] == ["CH1", "CH2"]
    np.testing.assert_allclose(files[0].signals[0].x[:3], [0, 1, 2])


def test_csv_import_windows_path(ctrl, csv_files):
    """Un chemin avec des '\\' (glisser-déposer, fichiers récents...) doit fonctionner."""
    win_path = csv_files[0].replace("/", "\\")
    files = load(ctrl, win_path)

    assert [f.name for f in files] == ["fileA"]
    # le menu des fichiers récents est reconstruit sans erreur
    recent = [a.text() for a in ctrl.view.recent_files_menu.actions()]
    assert recent == [win_path]


def test_recent_files_written_to_user_profile(ctrl, csv_files):
    load(ctrl, csv_files[0])
    with open(ctrl.menu_ctrl.user_config) as f:
        data = json.load(f)
    assert data["files"][0]["address"] == csv_files[0]
    # garde-fou : les tests ne doivent jamais écrire dans le vrai profil
    assert ctrl.menu_ctrl.user_config.startswith(os.environ["USERPROFILE"])
