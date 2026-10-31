# tests/test_plot_panels.py
"""
Graphique en panneaux (controller.plot_panel.PlotPanel) : un panneau principal par
défaut, compatibilité de plot / vb / curves, courbes réparties sur plusieurs panneaux.
"""
import numpy as np
import pytest

from controller.plot_panel import PlotPanel, SignalCurveItem
from helpers import load


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
    graph.updateOptions({"Y_title": "Puissance", "Y_unit": "W"})
    for panel in graph.panels:
        assert panel.yp_axis.labelText == "Puissance"


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
