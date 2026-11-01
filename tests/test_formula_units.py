# tests/test_formula_units.py
"""Homogénéité des formules (model.formula.units) et caloporteurs (model.formula.fluids)."""
import numpy as np
import pytest
from PyQt6 import QtCore, QtWidgets

from helpers import load
from model.formula import FormulaError, evaluate, fluids, parse, units


@pytest.fixture
def files(ctrl, csv_files):
    return list(load(ctrl, *csv_files))          # fileA, fileB : CH1, CH2


# ---------------- lecture des unités ----------------

@pytest.mark.parametrize("text, si, scale", [
    ("°C", "K", 1), ("�C", "K", 1), ("degC", "K", 1), ("K", "K", 1),
    ("L/min", "m³/s", 1e-3 / 60), ("m3/h", "m³/s", 1 / 3600), ("m³/s", "m³/s", 1),
    ("kg/m³", "kg/m³", 1), ("J/(kg·K)", "J/(kg·K)", 1), ("W/(m²·K)", "W/(m²·K)", 1),
    ("mV", "V", 1e-3), ("kW", "W", 1e3), ("uA", "A", 1e-6), ("mbar", "Pa", 100),
    ("kWh", "J", 3.6e6), ("V/A", "Ω", 1), ("Ohm", "Ω", 1), ("1/s", "Hz", 1),
    ("%RH", "sans dimension", 0.01),
])
def test_parse_unit(text, si, scale):
    unit = units.parse_unit(text)
    assert units.dims_text(unit.dims) == si
    assert unit.scale == pytest.approx(scale)
    assert unit.text == text


@pytest.mark.parametrize("text", ["", "dB", "W/(m", "kg²x"])
def test_unknown_unit(text):
    with pytest.raises(units.UnitError):
        units.parse_unit(text)


# ---------------- analyse d'une formule ----------------

UNITS = {"[Tin]": "°C", "[Tout]": "°C", "[P]": "W", "[Q]": "L/min", "[V]": "V",
         "[X]": "", "[Y]": "dB", "CH3": "A"}


def analyse(formula):
    return units.analyse(parse(formula), UNITS)


@pytest.mark.parametrize("formula, expected", [
    ("([Tout]-[Tin])/[P]", "K/W (résistance thermique)"),
    ("[P]/([Tout]-[Tin])", "W/K (conductance thermique)"),
    ("[Q]/60000*rho_water([Tin])*cp_water([Tin])*([Tout]-[Tin])", "W (puissance)"),
    ("[V]^2/[P]", "Ω (résistance électrique)"),
    ("[V]*CH3", "W (puissance)"),
    ("time*[P]", "J (énergie)"),
    ("sqrt([P]*[P])", "W (puissance)"),
    ("[Tin]+273.15", "°C (température)"),
    ("avg([Tin];[Tout])", "°C (température)"),
    ("max([P])", "W (puissance)"),
    ("2*[P]/1000", "W (puissance)"),
    ("-[P]", "W (puissance)"),
    ("exp(2)*3", "sans dimension"),
])
def test_result_unit(formula, expected):
    report = analyse(formula)
    assert report.issues == []
    assert units.describe(report.unit) == expected


@pytest.mark.parametrize("formula, issue", [
    ("[Tin]+[P]", "+ entre °C (température) et W (puissance)"),
    ("[P]-[V]", "- entre W"),
    ("max([P];[Tin])", "max(...) entre"),
    ("log([P])", "log d'une grandeur avec unité"),
    ("rho_water([P])", "rho_water attend une température"),
    ("[P]^[V]", "exposant avec unité"),
    ("[P]^time", "exposant avec unité"),
])
def test_inconsistent_formula(formula, issue):
    report = analyse(formula)
    assert report.unit is None
    assert any(text.startswith(issue) for text in report.issues), report.issues


@pytest.mark.parametrize("formula, note", [
    ("[X]*2", "[X] n'a pas d'unité"),
    ("[Y]+1", "unité « dB » de [Y] non reconnue"),
    ("steps(time;0;1;10;2)", "steps(...) : la table n'a pas d'unité"),
])
def test_undetermined_unit(formula, note):
    report = analyse(formula)
    assert report.unit is None and report.issues == []
    assert any(text.startswith(note) for text in report.notes), report.notes


def test_non_si_input_is_noted():
    report = analyse("[Q]*2")
    assert units.describe(report.unit) == "L/min (débit volumique)"
    assert report.notes == ["[Q] est en L/min, hors SI : 1 L/min = 1.667e-05 m³/s"]


def test_same_dimension():
    unit = analyse("([Tout]-[Tin])/[P]").unit
    assert units.same_dimension("°C/W", unit) is True
    assert units.same_dimension("K/kW", unit) is True
    assert units.same_dimension("W", unit) is False
    assert units.same_dimension("dB", unit) is None


# ---------------- caloporteurs ----------------

@pytest.mark.parametrize("call, value", [
    ("rho_water(20)", 998.21), ("cp_water(20)", 4184.1), ("k_water(20)", 0.5984),
    ("mu_water(20)", 1.0016e-3), ("rho_water(25)", (998.21 + 995.65) / 2),
    ("rho_air(20)", 101325 / (287.05 * 293.15)), ("cp_air(26.85)", 1007),
    ("k_air(26.85)", 0.0263), ("mu_air(26.85)", 18.46e-6),
])
def test_fluid_values(call, value):
    assert evaluate(parse(call), {}) == pytest.approx(value, rel=1e-3)


def test_fluid_on_signal_and_out_of_range():
    t = np.array([10.0, 20.0, 150.0, np.nan])
    rho = evaluate(parse("rho_water([T])"), {"[T]": t})
    np.testing.assert_allclose(rho[:2], [999.70, 998.21])
    assert np.isnan(rho[2:]).all()          # hors table, valeur manquante
    with pytest.raises(FormulaError, match="outside the table"):
        evaluate(parse("rho_water(150)"), {})
    with pytest.raises(FormulaError, match="expects 1 argument"):
        evaluate(parse("cp_air(20;3)"), {})


def test_every_property_unit_is_known():
    for name, prop in fluids.PROPERTIES.items():
        assert units.quantity(units.parse_unit(prop.unit).dims), name
        assert fluids.function_name(prop.fluid, name.split("_")[0]) == name


# ---------------- contrôleur et boîtes de saisie ----------------

def test_controller_units(ctrl, files):
    a, b = files
    a.signals[0].unit, a.signals[1].unit = "°C", "W"
    b.signals[0].unit, b.signals[1].unit = "°C", ""
    b.set_params({"label": "200 W"})
    assert ctrl.formula_channel_units(a) == {"time": "s", "[CH1]": "°C", "[CH2]": "W",
                                             "[200 W:CH1]": "°C"}
    report = ctrl.formula_units(a, {"formula": "([CH1]-[200 W:CH1])/[CH2]"})
    assert units.describe(report.unit) == "K/W (résistance thermique)"
    assert ctrl.formula_units(a, {"formula": "[nope]"}) is None


def _dialog(ctrl, file_obj, formula, unit=""):
    from ressources.custom_dialogs import FormulaDialog
    return FormulaDialog(ctrl.formula_channels(file_obj),
                         lambda params: ctrl.check_formula(file_obj, params),
                         {"formula": formula, "unit": unit},
                         units=ctrl.formula_channel_units(file_obj),
                         analyse=lambda params: ctrl.formula_units(file_obj, params))


def test_dialog_shows_computed_unit(ctrl, files):
    a = files[0]
    a.signals[0].unit, a.signals[1].unit = "°C", "W"
    dialog = _dialog(ctrl, a, "([CH1]-20)/[CH2]")
    assert "Unité calculée : K/W (résistance thermique)" in dialog.unit_info.text()
    assert dialog.use_unit.isEnabled()
    dialog.use_unit.click()
    assert dialog.unit.text() == "K/W" and not dialog.use_unit.isEnabled()
    assert dialog.unit_info.styleSheet() == dialog.UNIT_OK

    dialog.unit.setText("W")
    assert "≠ unité saisie « W »" in dialog.unit_info.text()
    assert dialog.unit_info.styleSheet() == dialog.UNIT_WARNING

    dialog.formula.setText("[CH1]+[CH2]")
    ok = dialog.buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok)
    assert ok.isEnabled()                   # incohérence signalée, pas bloquante
    assert "Formule non homogène" in dialog.unit_info.text()
    assert "unités incompatibles" in dialog.unit_info.text()

    dialog.formula.setText("[nope]")
    assert dialog.unit_info.text() == "" and not dialog.use_unit.isEnabled()


def test_dialog_lists_units_and_inserts_name(ctrl, files):
    a = files[0]
    a.signals[0].unit = "°C"
    dialog = _dialog(ctrl, a, "")
    item = dialog.channels.item(0)
    assert item.text() == "[CH1]    (°C)"
    dialog.channels.itemDoubleClicked.emit(item)
    assert dialog.formula.text() == "[CH1]"


def test_fluid_dialog_property():
    from ressources.custom_dialogs import FluidDialog
    dialog = FluidDialog(["[T eau]", "time"])
    assert dialog.call() == "rho_water(20)"
    assert "ρ(20 °C) = 998.21 kg/m³" in dialog.message.text()
    dialog.property.setCurrentIndex(1)
    dialog.fluid.setCurrentText("Air")
    dialog.temperature.setCurrentText("[T eau]")
    assert dialog.call() == "cp_air([T eau])"
    dialog.temperature.setCurrentText("500")
    ok = dialog.buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok)
    assert not ok.isEnabled() and "outside the table" in dialog.message.text()


@pytest.mark.parametrize("flow_unit, expected", [
    ("L/min", "[Débit eau]/60000*rho_water(avg([T entrée];[T sortie]))"
              "*cp_water(avg([T entrée];[T sortie]))*([T sortie]-[T entrée])"),
    ("m³/h", "[Débit eau]/3600*rho_water(avg([T entrée];[T sortie]))"
             "*cp_water(avg([T entrée];[T sortie]))*([T sortie]-[T entrée])"),
    ("kg/s", "[Débit eau]*cp_water(avg([T entrée];[T sortie]))*([T sortie]-[T entrée])"),
])
def test_fluid_dialog_power(flow_unit, expected):
    from ressources.custom_dialogs import FluidDialog
    channels = ["[T entrée]", "[T sortie]", "[Débit eau]", "time"]
    dialog = FluidDialog(channels, {"[Débit eau]": flow_unit})
    dialog.tabs.setCurrentIndex(dialog.POWER)
    # voies devinées d'après leur nom, unité du débit reprise de la voie
    assert (dialog.flow.currentText(), dialog.t_in.currentText(),
            dialog.t_out.currentText()) == ("[Débit eau]", "[T entrée]", "[T sortie]")
    assert dialog.flow_unit.text() == flow_unit
    assert dialog.call() == expected
    # la formule obtenue est homogène à une puissance
    report = units.analyse(parse(expected), {"[Débit eau]": flow_unit,
                                             "[T entrée]": "°C", "[T sortie]": "°C"})
    assert units.describe(report.unit) == "W (puissance)"


def test_fluid_dialog_power_value():
    # 6 L/min d'eau échauffée de 20 à 30 °C : environ 0,1 kg/s × 4180 × 10 = 4,2 kW
    from ressources.custom_dialogs import FluidDialog
    dialog = FluidDialog(["[Q]", "[Ti]", "[To]"], {"[Q]": "L/min"})
    dialog.tabs.setCurrentIndex(dialog.POWER)
    for box, text in ((dialog.flow, "[Q]"), (dialog.t_in, "[Ti]"), (dialog.t_out, "[To]")):
        box.setCurrentText(text)
    dialog.flow_unit.setText("L/min")
    power = evaluate(parse(dialog.call()), {"[Q]": 6.0, "[Ti]": 20.0, "[To]": 30.0})
    assert power == pytest.approx(6 / 60000 * 996.93 * 4182.1 * 10, rel=1e-3)


def test_fluid_dialog_rejects_bad_flow_unit():
    from ressources.custom_dialogs import FluidDialog
    dialog = FluidDialog(["[Q]", "[Ti]", "[To]"])
    dialog.tabs.setCurrentIndex(dialog.POWER)
    for box, text in ((dialog.flow, "[Q]"), (dialog.t_in, "[Ti]"), (dialog.t_out, "[To]")):
        box.setCurrentText(text)
    ok = dialog.buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok)
    assert not ok.isEnabled() and "unité du débit" in dialog.message.text()
    dialog.flow_unit.setText("W")
    assert not ok.isEnabled() and "n'est pas un débit" in dialog.message.text()
    dialog.flow_unit.setText("L/h")
    assert ok.isEnabled() and dialog.call().startswith("[Q]/3600000*")
