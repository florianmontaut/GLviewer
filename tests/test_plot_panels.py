# tests/test_plot_panels.py
"""
Graphique en panneaux (controller.plot_panel.PlotPanel) : un panneau principal par
défaut, compatibilité de plot / vb / curves, courbes réparties sur plusieurs panneaux,
une échelle verticale par unité dans un panneau.
"""
import numpy as np
import pytest
from PyQt6 import QtCore

from controller.plot_panel import PlotPanel, SignalCurveItem
from helpers import load
from test_hz_channels import write_gl820, _smooth


@pytest.fixture
def files(ctrl, csv_files):
    return list(load(ctrl, *csv_files))


def test_single_main_panel_by_default(ctrl, files):
    graph = ctrl.graph_ctrl
    assert len(graph.panels) == 1
    panel = graph.main_panel
    assert isinstance(panel, PlotPanel)
    assert graph.plot is panel.plot and graph.vb is panel.vb
    assert graph.curves is panel.curves
    assert all(isinstance(c, SignalCurveItem) for c in graph.curves.values())
    assert graph.panel_of(files[0].signals[0]) is panel


def test_options_applied_to_every_panel(ctrl, files):
    graph = ctrl.graph_ctrl
    second = graph.add_panel()
    graph.updateOptions({"Y_title": "Température", "Y_major_t": 5.0})
    for panel in graph.panels:
        assert panel.yp_axis.labelText == "Température"
        assert panel.yp_axis._tickSpacing[0][0] == 5.0


def test_curve_on_second_panel(ctrl, files):
    graph = ctrl.graph_ctrl
    second = graph.add_panel()
    sig = files[1].signals[0]
    graph.remove_signal_curve(sig)
    graph.add_signal_curve(sig, panel=second)

    assert graph.panel_of(sig) is second
    assert sig in graph.curves and sig not in graph.main_panel.curves
    assert len(graph.curves) == 4
    # panneaux empilés dans la même fenêtre graphique
    assert graph.graph.ci.getItem(1, 0) is second.plot

    sig.visible = False
    graph.update_signal(sig)
    assert not second.curves[sig].isVisible()
    graph.highlight(sig)
    assert second.curves[sig].opts["pen"].widthF() >= 2

    graph.remove_signal_curve(sig)
    assert sig not in graph.curves and graph.panel_of(sig) is None


def test_zoom_limits_per_panel(ctrl, files):
    graph = ctrl.graph_ctrl
    second = graph.add_panel()
    sig = files[1].signals[1]                       # sinus autour de 20
    graph.remove_signal_curve(sig)
    graph.add_signal_curve(sig, panel=second)
    graph.update_vbox()
    y_max = second.vb.state["limits"]["yLimits"][1]
    assert y_max < 25                               # seulement le sinus de ce panneau
    assert graph.main_panel.vb.state["limits"]["yLimits"][1] > 40


def test_nearest_sample_uses_curve_panel(ctrl, files, qapp):
    graph = ctrl.graph_ctrl
    second = graph.add_panel()
    ctrl.view.resize(1400, 900)
    ctrl.view.show()                                # mise en page réelle des panneaux
    qapp.processEvents()
    sig = files[1].signals[0]
    graph.remove_signal_curve(sig)
    graph.add_signal_curve(sig, panel=second)
    graph.update_vbox()
    scene = second.vb.mapViewToScene(second.vb.viewRect().center())
    x, y = graph.nearest_sample(sig, scene)
    assert x in sig.x and np.isfinite(y)
    assert graph.panel_at(scene) is second


# ---------------- une échelle par unité ----------------

def _set_unit(ctrl, sig, unit):
    """Unité modifiée dans le ParameterTree (Curve unit)."""
    from ressources.custom_items import SelectionContext, itemType
    ctrl._on_param_changed(SelectionContext(role=itemType.RAW, signal=sig), {"unit": unit})


def test_one_scale_per_unit(ctrl, files):
    graph = ctrl.graph_ctrl
    panel = graph.main_panel
    assert panel.units() == ["°C"] and not panel.scales
    assert not panel.plot.getAxis("right").isVisible()

    power = files[0].signals[1]
    _set_unit(ctrl, power, "W")
    assert panel.units() == ["°C", "W"]
    scale = panel.scales["W"]
    assert graph.curves[power].getViewBox() is scale.vb
    assert panel.plot.getAxis("right").isVisible()
    assert panel.plot.getAxis("right").labelText == "W"
    assert panel.plot.getAxis("right").linkedView() is scale.vb
    # échelle ajustée aux seules courbes en W (sinus autour de 20)
    s0, s1 = scale.vb.viewRange()[1]
    assert 18 < s0 < 19.5 and 20.5 < s1 < 22

    # troisième unité : axe supplémentaire à droite
    _set_unit(ctrl, files[1].signals[1], "V")
    assert list(panel.scales) == ["W", "V"]
    assert len(panel._extra_axes) == 1
    assert panel._extra_axes[0].labelText == "V"

    # retour en °C : échelles retirées, courbe sur l'échelle principale
    _set_unit(ctrl, power, "°C")
    _set_unit(ctrl, files[1].signals[1], "°C")
    assert not panel.scales and not panel._extra_axes
    assert graph.curves[power].getViewBox() is panel.vb
    assert not panel.plot.getAxis("right").isVisible()


def test_secondary_scale_follows_main_zoom(ctrl, files):
    graph = ctrl.graph_ctrl
    panel = graph.main_panel
    _set_unit(ctrl, files[0].signals[1], "W")
    scale = panel.scales["W"]
    graph.update_vbox()
    m0, m1 = panel.vb.viewRange()[1]
    s0, s1 = scale.vb.viewRange()[1]
    # zoom x2 sur le graphique : l'échelle en W suit
    panel.vb.setYRange(m0, m0 + (m1 - m0) / 2, padding=0)
    t0, t1 = scale.vb.viewRange()[1]
    assert t0 == pytest.approx(s0) and t1 - t0 == pytest.approx((s1 - s0) / 2)
    # axe des temps commun
    panel.vb.setXRange(100, 200, padding=0)
    assert scale.vb.viewRange()[0] == pytest.approx([100, 200])

    # échelle déplacée seule (glisser sur l'axe de droite) : relation conservée ensuite
    scale.vb.setYRange(0, 10, padding=0)
    scale.store_relation()
    a0, a1 = panel.vb.viewRange()[1]
    panel.vb.setYRange(a0 + 1, a1 + 1, padding=0)
    assert scale.vb.viewRange()[1][1] - scale.vb.viewRange()[1][0] == pytest.approx(10)


def test_zoom_limits_from_main_unit_only(ctrl, files):
    graph = ctrl.graph_ctrl
    panel = graph.main_panel
    for f in files:
        _set_unit(ctrl, f.signals[0], "W")           # échelons (25 -> 45) en W
    graph.update_vbox()
    y_max = panel.vb.state["limits"]["yLimits"][1]
    assert y_max < 25                                # seulement les sinus en °C


def test_nearest_sample_on_secondary_scale(ctrl, files, qapp):
    graph = ctrl.graph_ctrl
    panel = graph.main_panel
    ctrl.view.resize(1400, 900)
    ctrl.view.show()
    qapp.processEvents()
    sig = files[0].signals[1]
    _set_unit(ctrl, sig, "W")
    scale = panel.scales["W"]
    scale.vb.setYRange(0, 100, padding=0)           # sinus écrasé en bas du graphique
    scale.store_relation()
    qapp.processEvents()
    i = 300
    scene = scale.vb.mapViewToScene(QtCore.QPointF(sig.x[i], sig.y[i]))
    x, y = graph.nearest_sample(sig, scene)
    assert x == pytest.approx(sig.x[i], abs=3)


def test_gl_units_imported_and_saved(ctrl, tmp_path):
    path = write_gl820(tmp_path / "GL_units.csv", {"T AMB": _smooth(20, 5),
                                                   "Tension": _smooth(12, 1)})
    text = open(path, encoding="latin-1", newline="").read()
    old = "Tension;TEMP;TC_K;40;180.000000;0.000000;degC"
    assert old in text
    text = text.replace(old, "Tension;DC;20V;40;180.000000;0.000000;V")
    open(path, "w", encoding="latin-1", newline="").write(text)
    ctrl.import_ctrl.openGLCsvFiles(path)
    file_obj = ctrl.workspace.files[-1]
    assert [s.unit for s in file_obj.signals] == ["°C", "V"]
    assert ctrl.graph_ctrl.main_panel.units() == ["°C", "V"]

    # unité modifiée par l'utilisateur, conservée dans le projet
    _set_unit(ctrl, file_obj.signals[0], "K")
    project = tmp_path / "units.json"
    ctrl.workspace.save(project)
    ctrl.import_ctrl.openProject(str(project))
    assert [s.unit for s in ctrl.workspace.files[-1].signals] == ["K", "V"]


def test_derived_signal_uses_parent_unit(ctrl, files):
    from ressources.custom_types import qSignalType as T
    from helpers import add
    sig = files[0].signals[0]
    _set_unit(ctrl, sig, "W")
    ctrl.workspace_ctrl.push(sig, add(T.MODEL))
    derived = [s for s in ctrl.graph_ctrl.curves if getattr(s, "parent_signal", None) is sig]
    assert derived and all(s.unit == "W" for s in derived)
    scale = ctrl.graph_ctrl.main_panel.scales["W"]
    assert all(ctrl.graph_ctrl.curves[s].getViewBox() is scale.vb for s in derived)
