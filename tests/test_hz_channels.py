# tests/test_hz_channels.py
"""
Voies non exploitables (HZ : thermocouple sectionné, entrée du datalogger en l'air) :
détection à l'import, voie décochée, état sauvegardé dans le projet.
Les fichiers GL820 sont synthétiques, au format des exports .csv du datalogger.
"""
import numpy as np
import pandas as pd
import pytest
from PyQt6 import QtCore

from controller.import_controller import ImportController
from helpers import add


N = 1200
RNG = np.random.default_rng(1)
T = np.arange(N)


def _smooth(start=25.0, rise=40.0, tau=300.0):
    """Échauffement du 1er ordre, bruit de mesure de 0.1 °C."""
    return start + rise * (1 - np.exp(-T / tau)) + RNG.normal(0, 0.05, N)


def _floating_saturating():
    """Entrée en l'air : valeurs aux limites du TC K et sauts permanents (cas réel)."""
    y = RNG.choice([-270.0, 900.0], N) + RNG.normal(0, 50, N)
    y[RNG.random(N) < 0.3] = RNG.uniform(0, 180, (RNG.random(N) < 0.3).sum())[:1]
    return y


def _floating_in_span():
    """Entrée en l'air dont le bruit reste DANS la plage 0-180 °C."""
    return RNG.uniform(10, 170, N)


def _sectioned(at=0.3):
    """Thermocouple sectionné à 30 % de l'essai."""
    y = _smooth()
    cut = int(at * N)
    y[cut:] = RNG.choice([-270.0, 850.0], N - cut)
    return y


def write_gl820(path, channels, span=(0.0, 180.0)):
    """
    Écrit un export .csv GL820. channels : {nom: valeurs numériques ou chaînes}.
    span : (min, max) commun aux voies, ou dict {nom: (min, max)}.
    """
    names = list(channels)
    n_cols = len(names) + 5
    pad = lambda cells: ";".join(cells + [""] * (n_cols - len(cells)))
    lines = [pad(["Vendor", "GRAPHTEC Corporation"]),
             pad(["Model", "GL820"]),
             pad(["Sampling", "1s"]),
             pad(["Total data points", str(N)]),
             pad(["Trigger", "0"]),
             pad(["Start time", "09/11/2023", "09:55:37"]),
             pad(["Trigger time", "09/11/2023", "09:55:40"]),
             pad(["CH", " Signal name", " Input", " Range", " Filter", " Span"])]
    for i, name in enumerate(names, start=1):
        lo, hi = span[name] if isinstance(span, dict) else span
        lines.append(pad([f"CH{i}", name, "TEMP", "TC_K", "40", f"{hi:.6f}", f"{lo:.6f}", "degC"]))
    lines.append(pad(["Data"]))
    lines.append(pad(["No.", " Date&Time", " ms"] + [f"CH{i}" for i in range(1, len(names)+1)]))
    lines.append(pad(["NO.", "Time", "ms"] + ["degC"] * len(names)))
    for k in range(N):
        cells = [str(k+1), "09/11/2023 09:55", "0"]
        for name in names:
            v = channels[name][k]
            cells.append(v if isinstance(v, str) else f"{v:+.1f}")
        lines.append(pad(cells))
    # écriture binaire : en mode texte, Windows doublerait les \r des fins de ligne
    path.write_bytes(("\r\n".join(lines) + "\r\n").encode("latin-1"))
    return str(path).replace("\\", "/")


@pytest.fixture
def gl_file(tmp_path):
    return write_gl820(tmp_path / "GL820_test.csv", {
                        "T AMB"             : _smooth(20, 5),
                        "BOB PH1"           : _smooth(26, 100, 600),
                        "T dissip HZ"       : _floating_saturating(),
                        "Entree en l'air"   : _floating_in_span(),
                        "TC sectionne"      : _sectioned(),
                        "BURNOUT"           : ["BURNOUT"] * N,
                        "FER PH1"           : _smooth(29, 98, 500),
                        })


def _load(ctrl, path):
    ctrl.import_ctrl.openGLCsvFiles(path)
    return ctrl.workspace.files[-1]


def _hidden(file_obj):
    return [s.name for s in file_obj.signals if not s.visible]


EXPECTED_HZ = ["T dissip HZ", "Entree en l'air", "TC sectionne", "BURNOUT"]


# ---------------- détection ----------------

@pytest.mark.parametrize("values, valid", [
    (_smooth(), True),
    (_smooth(25, 140, 50), True),               # échauffement rapide, reste lisse
    (_floating_saturating(), False),
    (_floating_in_span(), False),               # non détecté avant : 100 % dans la plage
    (_sectioned(0.3), False),
    (np.full(N, -270.0), False),                # bloquée à la limite du TC
    (np.full(N, np.nan), False),                # BURNOUT / texte
])
def test_channel_validity(values, valid):
    assert ImportController.isChannelValid(pd.Series(values), (180.0, 0.0), True) is valid


def test_validity_check_can_be_disabled():
    assert ImportController.isChannelValid(pd.Series(_floating_in_span()), (180, 0), False)


# ---------------- chargement d'un fichier GL820 ----------------

def test_hz_channels_unchecked_at_load(ctrl, gl_file):
    file_obj = _load(ctrl, gl_file)

    assert _hidden(file_obj) == EXPECTED_HZ
    for sig in file_obj.signals:
        index = ctrl.model.signal_index(sig)
        state = ctrl.model.data(index, QtCore.Qt.ItemDataRole.CheckStateRole)
        expected = QtCore.Qt.CheckState.Unchecked if sig.name in EXPECTED_HZ \
                   else QtCore.Qt.CheckState.Checked
        assert state == expected
        assert ctrl.graph_ctrl.curves[sig].isVisible() is (sig.name not in EXPECTED_HZ)
    assert "4 voie(s)" in ctrl.view.statusbar.currentMessage()


def test_hidden_channels_do_not_drive_autorange(ctrl, gl_file):
    _load(ctrl, gl_file)
    (_, _), (ymin, ymax) = ctrl.graph_ctrl.vb.childrenBounds()
    assert ymin > 0 and ymax < 140


def test_user_can_recheck_hz_channel(ctrl, gl_file):
    file_obj = _load(ctrl, gl_file)
    sig = file_obj.signals[3]
    ctrl.model.setData(ctrl.model.signal_index(sig), QtCore.Qt.CheckState.Checked.value,
                       QtCore.Qt.ItemDataRole.CheckStateRole)
    assert sig.visible and ctrl.graph_ctrl.curves[sig].isVisible()


def test_negative_span_is_read_with_its_sign(ctrl, tmp_path):
    path = write_gl820(tmp_path / "neg.csv",
                       {"Froid": _smooth(-40, 30), "T AMB": _smooth(20, 5)},
                       span={"Froid": (-50.0, 50.0), "T AMB": (0.0, 180.0)})
    assert _hidden(_load(ctrl, path)) == []


def test_duplicate_channel_names(ctrl, tmp_path):
    path = write_gl820(tmp_path / "dup.csv", {"T": _smooth(20, 5), "T ": _smooth(30, 5)})
    # deux voies au même nom une fois les espaces retirés par le datalogger
    with open(path, "rb") as f:
        raw = f.read().replace(b";T ;", b";T;")
    with open(path, "wb") as f:
        f.write(raw)
    file_obj = _load(ctrl, path)
    names = [s.name for s in file_obj.signals]
    assert len(names) == 2 and len(set(names)) == 2


# ---------------- sauvegarde du filtrage dans le projet ----------------

def _save_and_reload(ctrl, tmp_path):
    project = tmp_path / "project.json"
    ctrl.workspace.save(project)
    ctrl.import_ctrl.openProject(str(project))
    return ctrl.workspace.files[0]


def test_hidden_channels_saved_in_project(ctrl, gl_file, tmp_path):
    _load(ctrl, gl_file)

    reloaded = _save_and_reload(ctrl, tmp_path)

    assert _hidden(reloaded) == EXPECTED_HZ
    for sig in reloaded.signals:
        assert ctrl.graph_ctrl.curves[sig].isVisible() is sig.visible


def test_user_choice_wins_over_detection_on_reload(ctrl, gl_file, tmp_path):
    file_obj = _load(ctrl, gl_file)
    rechecked, unchecked = file_obj.signals[3], file_obj.signals[0]
    for sig, state in ((rechecked, QtCore.Qt.CheckState.Checked),
                       (unchecked, QtCore.Qt.CheckState.Unchecked)):
        ctrl.model.setData(ctrl.model.signal_index(sig), state.value,
                           QtCore.Qt.ItemDataRole.CheckStateRole)

    reloaded = _save_and_reload(ctrl, tmp_path)

    hidden = _hidden(reloaded)
    assert rechecked.name not in hidden and unchecked.name in hidden
    assert ctrl.graph_ctrl.curves[reloaded.signals[3]].isVisible()
    assert not ctrl.graph_ctrl.curves[reloaded.signals[0]].isVisible()


def test_hidden_channel_keeps_its_filters_after_reload(ctrl, gl_file, tmp_path):
    from ressources.custom_types import qSignalType as T_
    file_obj = _load(ctrl, gl_file)
    ctrl.workspace_ctrl.push(file_obj.signals[1], add(T_.OFFSET, {"offset": 1.0}))
    reloaded = _save_and_reload(ctrl, tmp_path)
    assert len(reloaded.signals[1].pipeline) == 1 and _hidden(reloaded) == EXPECTED_HZ
