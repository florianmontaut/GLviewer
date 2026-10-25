# tests/test_lut.py
"""
Tables de correspondance dans les formules : steps(x; x1; y1...) (paliers, ex: puissance
du convertisseur) et interp(x; x1; y1...) (interpolation, ex: étalonnage d'un capteur),
et leur éditeur (tableau, collage depuis Excel).
"""
import numpy as np
import pytest
from PyQt6 import QtWidgets

from helpers import load
from model.formula import FormulaError, evaluate, parse
from model.formula.lut import format_call, parse_rows
from test_computed_channels import channel, dialog, files  # noqa: F401 (fixtures)

T = np.array([0.0, 100.0, 200.0, 200.5, 201.0, 300.0, 500.0])


def _eval(formula, **variables):
    return evaluate(parse(formula), variables)


# ---------------- steps / interp ----------------

def test_steps_power_profile():
    """De 0 à 200 s : 200 W, à partir de 201 s : 800 W."""
    out = _eval("steps(time; 0; 200; 201; 800)", time=T)
    np.testing.assert_allclose(out, [200, 200, 200, 200, 800, 800, 800])


def test_steps_before_first_point_and_missing_input():
    out = _eval("steps(time; 10; 1; 20; 2)", time=np.array([5.0, 10.0, np.nan, 25.0]))
    assert np.isnan(out[0]) and out[1] == 1 and np.isnan(out[2]) and out[3] == 2


def test_steps_back_to_zero_with_a_last_row():
    out = _eval("steps(time; 0; 200; 400; 0)", time=np.array([399.0, 400.0, 600.0]))
    np.testing.assert_allclose(out, [200, 0, 0])


def test_interp_calibration_curve():
    out = _eval("interp([V]; 0; -40; 5; 150)", **{"[V]": np.array([-1, 0, 2.5, 5, 6.0])})
    assert np.isnan(out[0])
    np.testing.assert_allclose(out[1:], [-40, 55, 150, 150])


def test_lut_in_an_expression():
    out = _eval("steps(time; 0; 200; 201; 800) * 0.95", time=T)
    np.testing.assert_allclose(out[[0, -1]], [190, 760])


@pytest.mark.parametrize("formula, message", [
    ("steps(time; 0; 200; 201)", "pairs"),
    ("steps(time)", "pairs"),
    ("interp(time; 10; 1; 5; 2)", "strictly increasing"),
    ("steps(time; 0; 1; 0; 2)", "strictly increasing"),
    ("steps(time; time; 1)", "numbers only"),
])
def test_invalid_tables(formula, message):
    with pytest.raises(FormulaError, match=message):
        _eval(formula, time=T)


def test_format_call_round_trip():
    rows = [(-10.5, -40.0), (1e-3, 0.25), (3600, 1500)]
    call = format_call("interp", "[T AMB]", rows)
    assert call == "interp([T AMB]; -10.5; -40; 0.001; 0.25; 3600; 1500)"
    np.testing.assert_allclose(_eval(call, **{"[T AMB]": np.array([-10.5, 3600.0])}),
                               [-40, 1500])


# ---------------- collage depuis Excel ----------------

def test_parse_rows_from_excel():
    text = "Temps\tPuissance\r\n0\t200\r\n201\t800,5\r\n\r\n"
    assert parse_rows(text) == [(0, 200), (201, 800.5)]
    assert parse_rows("0;200\n201;800\n") == [(0, 200), (201, 800)]
    assert parse_rows("0 200\n201 800") == [(0, 200), (201, 800)]
    # colonnes au-delà de la 2e ignorées
    assert parse_rows("0\t200\tcommentaire") == [(0, 200)]


def test_parse_rows_reports_a_bad_line():
    with pytest.raises(ValueError, match="Ligne 3"):
        parse_rows("x\ty\n0\t200\nabc\t800")


# ---------------- voie calculée ----------------

def test_power_channel_on_file_time(ctrl, files, dialog):
    sig = channel(ctrl, dialog, files[0], "steps(time; 0; 200; 201; 800)", name="P",
                  unit="W")
    assert not sig.error
    np.testing.assert_allclose(sig.y[[0, 200, 201, 599]], [200, 200, 800, 800])


def test_power_channel_follows_file_offset(ctrl, files, dialog):
    """time est le temps affiché : décaler le fichier décale les paliers."""
    a = files[0]
    sig = channel(ctrl, dialog, a, "steps(time; 0; 200; 201; 800)", name="P")
    a.set_params({"offset": 100.0})
    ctrl._refresh_derived()
    assert sig.x[0] == 100.0
    np.testing.assert_allclose(sig.y[[0, 100, 101]], [200, 200, 800])


def test_power_channel_saved_with_project(ctrl, files, dialog, tmp_path):
    channel(ctrl, dialog, files[0], "steps(time; 0; 200; 201; 800)", name="P")
    project = tmp_path / "lut.json"
    ctrl.workspace.save(project)
    ctrl.import_ctrl.openProject(str(project))
    sig = next(s for s in ctrl.workspace.files[0].signals if s.name == "P")
    np.testing.assert_allclose(sig.y[[0, 201]], [200, 800])


# ---------------- éditeur de table ----------------

@pytest.fixture
def lut_dialog(qapp):
    from ressources.custom_dialogs import LutDialog
    return LutDialog(["[CH1]", "[CH2]", "time"])


def _ok(dialog):
    return dialog.buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).isEnabled()


def test_lut_dialog_builds_steps_call(lut_dialog):
    assert not _ok(lut_dialog)                                    # table vide
    lut_dialog.set_rows([(0, 200), (201, 800)])
    assert _ok(lut_dialog)
    assert lut_dialog.call() == "steps(time; 0; 200; 201; 800)"
    assert lut_dialog.message.text() == lut_dialog.call()


def test_lut_dialog_interp_on_a_channel(lut_dialog):
    lut_dialog.set_rows([(0, -40), (5, 150)])
    lut_dialog.interp_mode.setChecked(True)
    lut_dialog.input.setCurrentText("[CH1]")
    assert lut_dialog.call() == "interp([CH1]; 0; -40; 5; 150)"


def test_lut_dialog_paste_from_excel(lut_dialog):
    lut_dialog.paste_text("Temps\tPuissance\n0\t200\n201\t800\n400\t0\n")
    assert lut_dialog.table.rowCount() == 3
    assert lut_dialog.call() == "steps(time; 0; 200; 201; 800; 400; 0)"
    # collé à la suite des lignes remplies
    lut_dialog.table.setCurrentCell(-1, -1)
    lut_dialog.paste_text("600\t100")
    assert lut_dialog.rows()[-1] == (600, 100)


def test_lut_dialog_rejects_invalid_tables(lut_dialog):
    lut_dialog.set_rows([(201, 800), (0, 200)])
    assert not _ok(lut_dialog) and "croissants" in lut_dialog.message.text()
    lut_dialog.set_rows([(0, 200), (201, 800)])
    lut_dialog.table.setItem(1, 1, QtWidgets.QTableWidgetItem("abc"))
    assert not _ok(lut_dialog) and "Ligne 2" in lut_dialog.message.text()
    lut_dialog.paste_text("x\ty\n0\t200\nabc\t1")
    assert not _ok(lut_dialog) and "Ligne 3" in lut_dialog.message.text()


def test_formula_dialog_inserts_table(ctrl, files, monkeypatch):
    from ressources import custom_dialogs

    class FakeLut:
        def __init__(self, channels, parent=None):
            self.channels = channels

        def exec(self):
            return QtWidgets.QDialog.DialogCode.Accepted

        def call(self):
            return "steps(time; 0; 200; 201; 800)"
    monkeypatch.setattr(custom_dialogs, "LutDialog", FakeLut)
    a = files[0]
    dialog = custom_dialogs.FormulaDialog(ctrl.formula_channels(a),
                                          lambda params: ctrl.check_formula(a, params),
                                          {"formula": ""})
    dialog.table_button.click()
    assert dialog.formula.text() == "steps(time; 0; 200; 201; 800)"
    assert _ok(dialog) and "de 200 à 800" in dialog.message.text()
