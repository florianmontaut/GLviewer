# tests/test_benchmark.py
"""
Fenêtre « Benchmark » (étape 5) : ΔT, Rth... des modèles thermiques d'une même voie dans
plusieurs essais, en fonction du point de fonctionnement lu dans l'étiquette du fichier.
"""
import numpy as np
import pytest

from conftest import _write_xy_csv
from model.benchmark import operating_point
from ressources.custom_types import qSignalType as T
from helpers import load, nodes

N = 600
T_AXIS = np.arange(N)


@pytest.fixture
def essais(ctrl, tmp_path):
    """Trois essais chargés dans le désordre : CH1 s'échauffe de 20 K par 100 W."""
    paths = []
    for name, rise in (("essai_c", 60), ("essai_a", 20), ("essai_b", 40)):
        path = tmp_path / f"{name}.csv"
        _write_xy_csv(path, N, 25 + rise * (1 - np.exp(-T_AXIS / 80)),
                      25 + rise / 2 * (1 - np.exp(-T_AXIS / 120)))
        paths.append(str(path).replace("\\", "/"))
    files = list(load(ctrl, *paths))
    for file_obj, label in zip(files, ("300 W", "100 W", "200 W")):
        file_obj.set_params({"label": label})
    ctrl.channel_model.rebuild()
    return files


def _models(ctrl, signals):
    ctrl.apply_to_signals(signals, T.MODEL)
    ctrl.graph_ctrl.range_picker.accepted.emit(signals[0], 0.0, float(N - 1))


@pytest.fixture
def bench(ctrl):
    ctrl.view.actionBenchmark.trigger()
    yield ctrl.benchmark_ctrl
    ctrl.benchmark_ctrl.window.close()


def _quantity(bench, label):
    combo = bench.window.quantity_combo
    combo.setCurrentIndex(next(i for i in range(combo.count())
                               if combo.itemText(i).startswith(label)))


@pytest.mark.parametrize("label, expected", [("100 W", (100.0, "W")),
                                             ("100 W / 55 °C", (100.0, "W")),
                                             ("1500V", (1500.0, "V")),
                                             ("2,5 kW", (2.5, "kW")),
                                             ("-20 °C", (-20.0, "°C")),
                                             ("référence", (None, "")),
                                             ("", (None, ""))])
def test_operating_point(label, expected):
    assert operating_point(label) == expected


def test_menu_opens_window_before_any_file(ctrl, bench):
    assert bench.window.isVisible()
    assert bench.channels == [] and bench.rows == []
    assert "Aucune voie" in bench.window.info.text()


def test_delta_t_and_rth(ctrl, essais, bench):
    _models(ctrl, [s for f in essais for s in f.signals])

    assert [row.name for row in bench.rows] == ["100 W", "200 W", "300 W"]   # triés
    assert [c.name for c in bench.channels] == ["CH1", "CH2"]
    lines = bench.table_lines()
    assert lines[0] == ["Essai", "Point de fonctionnement", "CH1 ΔT (K)", "CH2 ΔT (K)"]
    delta = [[float(v.replace(",", ".")) for v in line[2:]] for line in lines[1:]]
    np.testing.assert_allclose(delta, [[20, 10], [40, 20], [60, 30]], rtol=0.02)

    _quantity(bench, "Rth")                      # puissance du modèle : 100 W par défaut
    rth = [[float(v.replace(",", ".")) for v in line[2:]] for line in bench.table_lines()[1:]]
    np.testing.assert_allclose(rth, np.array(delta) / 100, rtol=1e-6)

    table = bench.window.table
    assert table.rowCount() == 3 and table.columnCount() == 3
    assert table.item(0, 0).text() == "100 W"
    assert "Puissance du modèle : 100 W" in table.item(0, 1).toolTip()


def test_plot_one_curve_per_channel(ctrl, essais, bench):
    _models(ctrl, [s for f in essais for s in f.signals])
    curves = bench.window.plot.getPlotItem().listDataItems()
    assert len(curves) == 2
    x, y = curves[0].getData()
    np.testing.assert_allclose(x, [100, 200, 300])
    np.testing.assert_allclose(y, [20, 40, 60], rtol=0.02)
    assert "Point de fonctionnement (W)" in bench.window.plot.getPlotItem() \
        .getAxis("bottom").labelText


def test_missing_model_shown_as_dash(ctrl, essais, bench):
    _models(ctrl, [essais[1].signals[0], essais[2].signals[0]])        # pas à 300 W
    assert bench.table_lines()[3] == ["300 W", "300", ""]
    assert bench.window.table.item(2, 1).text() == "—"
    x, y = bench.window.plot.getPlotItem().listDataItems()[0].getData()
    np.testing.assert_allclose(x, [100, 200])


def test_without_numbers_in_labels(ctrl, essais, bench):
    for file_obj, label in zip(essais, ("c", "a", "")):
        file_obj.set_params({"label": label})
    ctrl.channel_model.rebuild()
    _models(ctrl, [f.signals[0] for f in essais])
    assert [row.name for row in bench.rows] == ["c", "a", "essai_b"]   # ordre de chargement
    x, _ = bench.window.plot.getPlotItem().listDataItems()[0].getData()
    np.testing.assert_allclose(x, [1, 2, 3])


def test_follows_undo_and_labels(ctrl, essais, bench, qapp):
    _models(ctrl, [f.signals[0] for f in essais])
    ctrl.workspace_ctrl.undo_stack.undo()
    assert bench.channels == []
    ctrl.workspace_ctrl.undo_stack.redo()
    assert [c.name for c in bench.channels] == ["CH1"]

    item = ctrl.model.find_item(ctrl.model.root, essais[1])
    ctrl.view.treefile.setCurrentIndex(ctrl.model.index_from_item(item))
    ctrl.param_ctrl.param.child("Label").setValue("400 W")
    qapp.processEvents()
    assert [row.name for row in bench.rows] == ["200 W", "300 W", "400 W"]


def test_user_group_selection(ctrl, essais, bench, monkeypatch):
    _models(ctrl, [s for f in essais for s in f.signals])
    monkeypatch.setattr(ctrl, "_ask_group_name", lambda title, default: "Sinus")
    ch2 = next(g.key for g in ctrl.channel_model.groups() if g.name == "CH2")
    ctrl.edit_channel_groups("new", [ch2])
    combo = bench.window.channels_combo
    assert [combo.itemText(i) for i in range(combo.count())] == \
           ["Voies avec un modèle thermique", "Groupe Sinus"]
    combo.setCurrentIndex(1)
    assert [c.name for c in bench.channels] == ["CH2"]
    bench.refresh()                          # le choix du groupe survit au rafraîchissement
    assert combo.currentText() == "Groupe Sinus"


def test_export_csv_and_image(ctrl, essais, bench, tmp_path):
    _models(ctrl, [f.signals[0] for f in essais])
    _quantity(bench, "Rth")
    csv_path = tmp_path / "bench.csv"
    bench.export_csv(csv_path)
    text = csv_path.read_text(encoding="utf-8-sig").splitlines()
    assert text[0] == "Essai;Point de fonctionnement;CH1 Rth (K/W)"
    assert text[1] == "100 W;100;0,2"                 # virgule décimale (Excel français)

    png = tmp_path / "bench.png"
    bench.export_image(png)
    assert png.stat().st_size > 1000
