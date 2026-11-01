# tests/test_dalo_import.py
"""
Enregistrements d'événement FLXDrive (DALO, .csv) : lecture (model.dalo_import), fichier
DaloFileObject (informations de l'événement, couleurs Matis, voies logiques), import,
projet. Les fichiers sont synthétiques, au format des exports du logger.
"""
import numpy as np
import pytest
from PyQt6 import QtCore, QtWidgets

from model.dalo_file import DaloFileObject
from model.dalo_import import COLORS, is_dalo, parse_dalo
from ressources.custom_exceptions import DaloStructureError
from ressources.custom_items import SelectionContext, itemType
from ressources.custom_types import fileType

PRE, POST, PERIOD = 5, 3, 0.001                      # 5 points avant le déclenchement


def write_dalo(path, n=PRE + POST, analog=None, digital=None, header=True, trailing=True):
    """Écrit un enregistrement d'événement : 3 voies analogiques, 2 logiques par défaut."""
    analog = analog or {"VbusP": np.linspace(600, 610, n), "INV2_Iph1": np.sin(np.arange(n)),
                        "CAN_Thr": np.full(n, 7600.0)}
    digital = digital or {"Pump1_On": np.arange(n) % 2, "Fan1_On": np.ones(n)}
    names = list(analog) + list(digital)
    end = ";" if trailing else ""
    lines = ["*" * 77, "***" + " " * 21 + "FAIVELEY TRANSPORT TOURS" + " " * 29 + "***",
             "***" + " " * 21 + "Rue Amélia EARHART" + " " * 35 + "***", "*" * 77,
             "", "FLXDrive", "", "CHILLER", ""]
    if header:
        lines += ["Equipment serial number: 6", "App version: 1.2.0.6, 0/0/0, 0:0:0", "",
                  "Date of event: 02/07/0026", "Time of event: 17:59:19", "",
                  f"Number of pre-trigger samples: {PRE}",
                  f"Number of post-trigger samples: {POST}",
                  f"Number of analog traces: {len(analog)}",
                  f"Number of logical traces: {len(digital)}",
                  f"Sampling Period in ns: {PERIOD * 1e9:.0f}", "", "File Id: 9", "",
                  "Event name: F_INV2_OverI_CanThreshold", "Event number of occurences: 1",
                  ""]
    lines += ["Range max value:;" + ";".join(["900", "300", "65600"] + ["1"] * len(digital)),
              "Range min value:;" + ";".join(["0", "-600", "-5"] + ["0"] * len(digital)),
              "Color:;YELLOW;WHITE;LIGHT_RED",
              "Time (s);" + ";".join(names) + end]
    for k in range(n):
        cells = [f"{(k - PRE) * PERIOD:g}"]
        cells += [f"{analog[name][k]:g}" for name in analog]
        cells += [f"{digital[name][k]:g}" for name in digital]
        lines.append(";".join(cells) + end)
    path.write_bytes(("\r\n".join(lines) + "\r\n").encode("latin-1"))
    return str(path).replace("\\", "/")


@pytest.fixture
def dalo_path(tmp_path):
    return write_dalo(tmp_path / "FLXDrive_CHILLER_event.csv")


@pytest.fixture
def dalo_file(ctrl, dalo_path):
    ctrl.import_ctrl.openDalo(dalo_path)
    return ctrl.workspace.files[-1]


# ---------------- lecture ----------------

def test_parse_header_channels_and_data(dalo_path):
    result = parse_dalo(dalo_path)

    assert list(result.data.columns) == ["Time", "VbusP", "INV2_Iph1", "CAN_Thr",
                                         "Pump1_On", "Fan1_On"]
    assert len(result.data) == PRE + POST
    assert result.sampling == pytest.approx(PERIOD)
    np.testing.assert_allclose(result.data["Time"].iloc[[0, PRE, -1]],
                               [-PRE * PERIOD, 0.0, (POST - 1) * PERIOD])
    vbus, iph, can, pump, fan = result.channels
    assert (vbus["min"], vbus["max"]) == (0, 900)                  # pas d'inversion
    assert (iph["min"], iph["max"]) == (-600, 300)
    assert [c["color"] for c in result.channels] == ["YELLOW", "WHITE", "LIGHT_RED",
                                                     None, None]
    assert [c["digital"] for c in result.channels] == [False] * 3 + [True] * 2
    assert result.event["Event name"] == "F_INV2_OverI_CanThreshold"
    assert result.event["Event date"] == "02/07/0026"
    assert result.event["Occurrences"] == "1"
    assert result.title == "F_INV2_OverI_CanThreshold — 02/07/0026 17:59:19"


def test_parse_without_trailing_separator_or_header(tmp_path):
    result = parse_dalo(write_dalo(tmp_path / "e.csv", header=False, trailing=False))
    assert len(result.channels) == 5
    # sans en-tête : période déduite du temps, voies logiques d'après leur plage 0-1
    assert result.sampling == pytest.approx(PERIOD)
    assert [c["digital"] for c in result.channels] == [False] * 3 + [True] * 2


def test_non_numeric_cells_are_missing(tmp_path):
    path = tmp_path / "e.csv"
    write_dalo(path)
    text = path.read_bytes().decode("latin-1")
    assert "\r\n-0.005;600;" in text                      # 1re ligne de données
    path.write_bytes(text.replace("\r\n-0.005;600;", "\r\n-0.005;ERROR;", 1)
                         .encode("latin-1"))
    result = parse_dalo(str(path))
    assert result.invalid_cells == 1 and np.isnan(result.data["VbusP"][0])


def test_not_a_dalo_file(tmp_path, csv_files):
    assert not is_dalo(csv_files[0])
    path = tmp_path / "other.csv"
    path.write_text("Time;CH1\n0;1\n")
    with pytest.raises(DaloStructureError):
        parse_dalo(str(path))


def test_is_dalo(dalo_path):
    assert is_dalo(dalo_path)


# ---------------- import ----------------

def test_import_creates_dalo_file(ctrl, dalo_file):
    assert isinstance(dalo_file, DaloFileObject)
    assert dalo_file.file_type == fileType.DALO.name
    vbus, iph, can, pump, fan = dalo_file.signals
    assert vbus.x[0] == pytest.approx(-PRE * PERIOD)              # 0 = déclenchement
    # couleurs Matis (WHITE en gris foncé), voies logiques : palette par défaut
    assert vbus.pen.color().name().upper() == COLORS["YELLOW"]
    assert iph.pen.color().name().upper() == COLORS["WHITE"]
    assert [s.is_digital for s in dalo_file.signals] == [False] * 3 + [True] * 2
    assert all(s.unit == "" and s.visible for s in dalo_file.signals)
    assert [s.name for s in ctrl.graph_ctrl.curves] == [s.name for s in dalo_file.signals]


def test_event_information_in_parameters_and_tooltip(ctrl, dalo_file):
    ctrl.param_ctrl.load_params(SelectionContext(role=itemType.FILE, signal=dalo_file))
    info = ctrl.param_ctrl.param.child("Event informations")
    assert info.child("Event name").value() == "F_INV2_OverI_CanThreshold"
    assert info.child("Date").value() == "02/07/0026"
    assert info.child("Event name").readonly()
    index = ctrl.model.index_from_item(ctrl.model.find_item(ctrl.model.root, dalo_file))
    tip = ctrl.model.data(index, QtCore.Qt.ItemDataRole.ToolTipRole)
    assert "Event name : F_INV2_OverI_CanThreshold" in tip


def test_time_offset_and_period_keep_trigger_origin(ctrl, dalo_file):
    ctx = SelectionContext(role=itemType.FILE, signal=dalo_file)
    ctrl._modify_file_params(ctx, {"offset": 1.0})
    assert dalo_file.signals[0].x[0] == pytest.approx(1.0 - PRE * PERIOD)
    ctrl._modify_file_params(ctx, {"offset": 0.0, "sampling": 2 * PERIOD})
    assert dalo_file.signals[0].x[0] == pytest.approx(-PRE * PERIOD)
    assert dalo_file.signals[0].x[1] == pytest.approx(-PRE * PERIOD + 2 * PERIOD)


def test_dalo_detected_from_graphtec_menu(ctrl, dalo_path, monkeypatch):
    monkeypatch.setattr(QtWidgets.QFileDialog, "getOpenFileName",
                        lambda *a, **k: (dalo_path, ""))
    ctrl.import_ctrl.load_file_dialog(fileType.GL)
    assert isinstance(ctrl.workspace.files[-1], DaloFileObject)


def test_invalid_dalo_reported_without_import_wizard(ctrl, tmp_path, monkeypatch,
                                                     warnings_shown):
    path = tmp_path / "broken.csv"
    path.write_text("Sampling Period in ns: 1000\nRange max value:;1\n")
    monkeypatch.setattr(QtWidgets.QFileDialog, "getOpenFileName",
                        lambda *a, **k: (str(path), ""))
    wizard = []
    monkeypatch.setattr(ctrl.import_ctrl, "ImportWizard", lambda *a, **k: wizard.append(a))

    ctrl.import_ctrl.load_file_dialog(fileType.DALO)

    assert not wizard and not ctrl.workspace.files
    assert "FLXDrive" in str(warnings_shown[0]) or "voies" in str(warnings_shown[0])


def test_project_round_trip(ctrl, dalo_file, tmp_path):
    dalo_file.signals[0].unit = "V"
    project = tmp_path / "events.json"
    ctrl.workspace.save(project)

    ctrl.import_ctrl.openProject(str(project))

    reloaded = ctrl.workspace.files[0]
    assert isinstance(reloaded, DaloFileObject)
    assert reloaded.event_name == "F_INV2_OverI_CanThreshold"
    assert [s.is_digital for s in reloaded.signals] == [False] * 3 + [True] * 2
    assert reloaded.signals[0].unit == "V"                         # unité enregistrée
    assert reloaded.signals[0].x[0] == pytest.approx(-PRE * PERIOD)


# ---------------- origine des temps des autres fichiers ----------------

def test_txt_time_column_origin_kept_with_offset(ctrl, tmp_path):
    """Colonne temps d'un .txt commençant à 10 s : le décalage s'y ajoute."""
    path = tmp_path / "late.txt"
    path.write_text("t;A\n" + "".join(f"{10 + k};{k}\n" for k in range(5)))
    ctrl.import_ctrl.openTxt(str(path), {"delim": ";", "unitdelim": ".", "start": 0,
                                          "columns": [], "sigNames": True,
                                          "isFirstColIndex": True})
    file_obj = ctrl.workspace.files[-1]
    assert file_obj.signals[0].x[0] == 10.0
    ctrl._modify_file_params(SelectionContext(role=itemType.FILE, signal=file_obj),
                             {"offset": 5.0})
    assert file_obj.signals[0].x[0] == 15.0
