# tests/test_missing_data.py
"""
Données manquantes (BURNOUT d'un GL, cellule vide...) : NaN dans les données, exclues
des calculs (filtres, FFT, modèle thermique, formules), affichées par une interruption
de la courbe ou par une valeur de remplacement (option « Missing data » du graphique).
"""
import numpy as np
import pytest
from PyQt6 import QtCore

from helpers import add
from model.analysis.thermal import ThermalModelAnalysis, thermal_step
from model.filters.lowpass import LowPassFilter
from model.filters.moving_average import MovingAverageFilter
from model.formula import evaluate, parse
from model.missing_data import display_values, fill_gaps, valid_on
from ressources.custom_types import qSignalType as T
from test_hz_channels import N, _smooth, write_gl820

GAP = slice(400, 430)            # BURNOUT de 30 s au milieu de l'essai


def _with_gap(y, gap=GAP):
    y = np.array(y, dtype=float)
    y[gap] = np.nan
    return y


@pytest.fixture
def burnout_file(ctrl, tmp_path):
    """Fichier GL820 : T1 avec 30 s de BURNOUT, T2 complète."""
    t1 = [f"{v:+.1f}" for v in _smooth()]
    t1[GAP] = ["BURNOUT"] * (GAP.stop - GAP.start)
    path = write_gl820(tmp_path / "burnout.csv", {"T1": t1, "T2": _smooth()})
    ctrl.import_ctrl.openGLCsvFiles(path)
    return ctrl.workspace.files[0]


# ---------------- import ----------------

def test_gl_burnout_is_missing_not_minus_20(burnout_file):
    t1 = burnout_file.signals[0]
    assert np.isnan(t1.raw_y[GAP]).all()
    assert np.isfinite(np.delete(t1.raw_y, np.r_[GAP])).all()
    assert not (t1.raw_y == -20).any()
    # 30 points manquants sur 1200 : la voie reste exploitable (pas masquée comme HZ)
    assert t1.visible


# ---------------- outils ----------------

def test_fill_gaps_interpolates_and_reports_missing():
    x = np.arange(6.0)
    filled, missing = fill_gaps(x, [0, np.nan, 2, np.nan, np.nan, 5])
    np.testing.assert_allclose(filled, [0, 1, 2, 3, 4, 5])
    assert missing.tolist() == [False, True, False, True, True, False]
    # bords : valeur valide la plus proche ; aucun point valide : inchangé
    np.testing.assert_allclose(fill_gaps(None, [np.nan, 1, 2, np.nan])[0], [1, 1, 2, 2])
    assert fill_gaps(None, [np.nan, np.nan])[1].all()


def test_valid_on_marks_instants_inside_a_gap():
    t_src = np.arange(5.0)
    y_src = [0, 1, np.nan, 3, 4]
    assert valid_on(t_src, y_src, [0.5, 1.5, 2.0, 3.0, 3.5]).tolist() == \
           [True, False, False, True, True]


def test_display_values():
    y = np.array([1.0, np.nan, 3.0])
    assert display_values(y, None) is y
    np.testing.assert_allclose(display_values(y, -20.0), [1, -20, 3])


# ---------------- filtres ----------------

def test_lowpass_keeps_valid_samples_around_a_gap():
    x = np.arange(N, dtype=float)
    y = _smooth()
    f = LowPassFilter(cutoff=0.05, fs=1.0, order=2)

    out = f.apply(x, _with_gap(y))

    assert np.isnan(out[GAP]).all()
    valid = np.ones(N, bool)
    valid[GAP] = False
    assert np.isfinite(out[valid]).all()
    # loin du trou, le filtrage est celui du signal complet
    far = np.r_[0:300, 530:N]
    np.testing.assert_allclose(out[far], f.apply(x, y)[far], atol=0.05)


def test_lowpass_on_fully_missing_signal():
    out = LowPassFilter(cutoff=0.05, fs=1.0, order=2).apply(None, np.full(50, np.nan))
    assert np.isnan(out).all()


def test_moving_average_ignores_missing_samples():
    y = np.full(20, 10.0)
    y[8] = np.nan
    out = MovingAverageFilter(window=5).apply(None, y)
    assert np.isnan(out[8])
    # voisins non contaminés, et bords non tirés vers 0
    np.testing.assert_allclose(np.delete(out, 8), 10.0)


# ---------------- analyses ----------------

def test_fft_with_a_few_missing_samples(ctrl, burnout_file, warnings_shown):
    t1 = burnout_file.signals[0]
    assert ctrl.workspace_ctrl.push(t1, add(T.FFT))
    assert np.isfinite(t1.derived_signals[0].y).all()
    assert not warnings_shown


def test_fft_refused_when_too_much_data_is_missing(ctrl, tmp_path, warnings_shown):
    t1 = [f"{v:+.1f}" for v in _smooth()]
    t1[:300] = ["BURNOUT"] * 300                         # 25 % de données manquantes
    path = write_gl820(tmp_path / "gaps.csv", {"T1": t1, "T2": _smooth()})
    ctrl.import_ctrl.openGLCsvFiles(path)
    t1 = ctrl.workspace.files[0].signals[0]

    assert not ctrl.workspace_ctrl.push(t1, add(T.FFT))
    assert not t1.analyses
    assert "manquantes" in str(warnings_shown[0])


def test_thermal_fit_excludes_missing_samples():
    x = np.arange(N, dtype=float)
    y = thermal_step(x, 65.0, 300.0, 25.0)

    def fit(values):
        analysis = ThermalModelAnalysis()
        analysis.set_fit_range(0.0, float(N - 1))
        return analysis.run(x, values, power=100.0)

    complete, with_gap = fit(y), fit(_with_gap(y))
    assert with_gap.tau == pytest.approx(complete.tau, rel=1e-3)
    assert with_gap.T_inf == pytest.approx(complete.T_inf, rel=1e-3)


def test_thermal_model_starts_at_first_valid_sample(ctrl, tmp_path):
    """Premiers échantillons manquants : la courbe modèle reste calée sur les données."""
    t1 = [f"{v:+.1f}" for v in _smooth()]
    t1[:50] = ["BURNOUT"] * 50
    path = write_gl820(tmp_path / "late.csv", {"T1": t1, "T2": _smooth()})
    ctrl.import_ctrl.openGLCsvFiles(path)
    sig = ctrl.workspace.files[0].signals[0]

    assert ctrl.workspace_ctrl.push(sig, add(T.MODEL))

    model = sig.derived_signals[0]
    assert model.x[0] == pytest.approx(sig.x[50])
    # le modèle suit la mesure sur la plage de fit
    measured = np.interp(model.x, sig.x, sig.y)
    inside = model.x <= sig.x[-1]
    assert np.nanmax(np.abs(model.y[inside] - measured[inside])) < 0.5


def test_external_diff_keeps_gap_missing(ctrl, burnout_file, csv_files):
    ctrl.import_ctrl.openCsvFiles(csv_files[0])
    t1, ref = burnout_file.signals[0], ctrl.workspace.files[1].signals[0]
    ctrl.workspace.set_reference_signal(ref)
    assert ctrl.workspace_ctrl.push(t1, add(T.DIFF_EXT, {"reference": ref,
                                                         "interp": "cubic"}))
    diff = t1.derived_signals[0]
    in_gap = (diff.x >= t1.x[GAP.start]) & (diff.x <= t1.x[GAP.stop - 1])
    assert np.isnan(diff.y[in_gap]).all()
    assert np.isfinite(diff.y[~in_gap]).mean() > 0.95      # trou seulement


# ---------------- formules ----------------

def test_formula_reductions_ignore_missing_samples():
    values = {"[T]": np.array([1.0, np.nan, 5.0])}
    for formula, expected in (("max([T])", 5), ("min([T])", 1), ("sum([T])", 6),
                              ("avg([T])", 3)):
        assert evaluate(parse(formula), values) == expected
    assert np.isnan(evaluate(parse("sum([T])"), {"[T]": np.full(3, np.nan)}))
    # élément par élément : un échantillon manquant reste manquant
    out = evaluate(parse("max([T];2)"), values)
    assert out[0] == 2 and np.isnan(out[1]) and out[2] == 5


# ---------------- affichage ----------------

def test_cursor_value_on_missing_sample(ctrl, burnout_file):
    t1 = burnout_file.signals[0]
    ctrl.model.updateCursorVal(float(t1.x[GAP.start + 5]))
    index = ctrl.model.signal_index(t1).siblingAtColumn(1)
    assert ctrl.model.data(index, QtCore.Qt.ItemDataRole.DisplayRole) == "-"


def test_gap_display_by_default(ctrl, burnout_file):
    curve = ctrl.graph_ctrl.curves[burnout_file.signals[0]]
    assert np.isnan(curve.yData[GAP]).all()


def test_placeholder_display_option(ctrl, burnout_file):
    t1 = burnout_file.signals[0]
    curve = ctrl.graph_ctrl.curves[t1]

    ctrl.graph_ctrl.updateOptions({"missing_display": "Placeholder value",
                                   "missing_value": -20.0})

    np.testing.assert_allclose(curve.yData[GAP], -20.0)
    # affichage seulement : les données et les calculs gardent les NaN
    assert np.isnan(t1.y[GAP]).all()
    # la valeur de remplacement reste dans les limites de zoom
    assert ctrl.graph_ctrl.vb.state["limits"]["yLimits"][0] < -20.0

    ctrl.graph_ctrl.updateOptions({"missing_display": "Gap in the curve"})
    assert np.isnan(curve.yData[GAP]).all()


def test_placeholder_display_follows_filters(ctrl, burnout_file):
    t1 = burnout_file.signals[0]
    ctrl.graph_ctrl.updateOptions({"missing_display": "Placeholder value",
                                   "missing_value": -20.0})
    ctrl.workspace_ctrl.push(t1, add(T.OFFSET, {"offset": 1.0}))
    curve = ctrl.graph_ctrl.curves[t1]
    np.testing.assert_allclose(curve.yData[GAP], -20.0)
    np.testing.assert_allclose(curve.yData[:10], t1.raw_y[:10] + 1.0)
