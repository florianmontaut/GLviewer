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


def _set_graph(ctrl, sig, number):
    """Paramètre « Graph » modifié dans le ParameterTree."""
    from ressources.custom_items import SelectionContext, itemType
    ctrl._on_param_changed(SelectionContext(role=itemType.RAW, signal=sig),
                           {"graph_number": number})


def test_curve_on_second_panel(ctrl, files):
    graph = ctrl.graph_ctrl
    sig = files[1].signals[0]
    _set_graph(ctrl, sig, 2)
    assert len(graph.panels) == 2
    second = graph.panels[1]

    assert graph.panel_of(sig) is second
    assert sig in graph.curves and sig not in graph.main_panel.curves
    assert len(graph.curves) == 4
    # panneaux empilés dans la même fenêtre graphique, axe des temps commun
    assert graph.graph.ci.getItem(1, 0) is second.plot
    assert second.vb.linkedView(second.vb.XAxis) is graph.main_panel.vb
    # titre de l'axe des temps sous le dernier panneau seulement
    assert second.xp_axis.label.isVisible() and not graph.main_panel.xp_axis.label.isVisible()

    sig.visible = False
    graph.update_signal(sig)
    assert not second.curves[sig].isVisible()
    graph.highlight(sig)
    assert second.curves[sig].opts["pen"].widthF() >= 2

    # retour dans le 1er graphique : panneau vide retiré
    _set_graph(ctrl, sig, 1)
    assert len(graph.panels) == 1 and graph.panel_of(sig) is graph.main_panel
    assert graph.main_panel.xp_axis.label.isVisible()


def test_graph_number_creates_intermediate_panels(ctrl, files):
    graph = ctrl.graph_ctrl
    sig = files[0].signals[0]
    _set_graph(ctrl, sig, 3)
    assert len(graph.panels) == 3 and graph.panel_of(sig) is graph.panels[2]
    graph.remove_signal_curve(sig)
    assert len(graph.panels) == 1


def test_zoom_limits_per_panel(ctrl, files):
    graph = ctrl.graph_ctrl
    sig = files[1].signals[1]                       # sinus autour de 20
    _set_graph(ctrl, sig, 2)
    second = graph.panels[1]
    graph.update_vbox()
    y_max = second.vb.state["limits"]["yLimits"][1]
    assert y_max < 25                               # seulement le sinus de ce panneau
    assert graph.main_panel.vb.state["limits"]["yLimits"][1] > 40


def test_nearest_sample_uses_curve_panel(ctrl, files, qapp):
    graph = ctrl.graph_ctrl
    ctrl.view.resize(1400, 900)
    ctrl.view.show()                                # mise en page réelle des panneaux
    qapp.processEvents()
    sig = files[1].signals[0]
    _set_graph(ctrl, sig, 2)
    second = graph.panels[1]
    graph.update_vbox()
    qapp.processEvents()
    scene = second.vb.mapViewToScene(second.vb.viewRect().center())
    x, y = graph.nearest_sample(sig, scene)
    assert x in sig.x and np.isfinite(y)
    assert graph.panel_at(scene) is second


def test_derived_curves_follow_their_signal(ctrl, files):
    from ressources.custom_types import qSignalType as T
    from helpers import add
    graph = ctrl.graph_ctrl
    sig = files[0].signals[0]
    ctrl.workspace_ctrl.push(sig, add(T.MODEL))
    _set_graph(ctrl, sig, 2)
    derived = [s for s in graph.curves if getattr(s, "parent_signal", None) is sig]
    assert derived and all(graph.panel_of(s) is graph.panels[1] for s in derived)


def test_context_menu_in_every_panel(ctrl, files):
    graph = ctrl.graph_ctrl
    _set_graph(ctrl, files[0].signals[0], 2)
    main_menu, second_menu = (p.vb.menu for p in graph.panels)
    shared = main_menu.actions()[:main_menu.actions().index(main_menu.viewAll)]
    assert shared and all(a in second_menu.actions() for a in shared)


def test_graph_number_saved_in_project(ctrl, files, tmp_path):
    graph = ctrl.graph_ctrl
    _set_graph(ctrl, files[1].signals[1], 2)
    project = tmp_path / "panels.json"
    ctrl.workspace.save(project)
    ctrl.import_ctrl.openProject(str(project))
    reloaded = ctrl.workspace.files[1].signals[1]
    assert reloaded.graph_number == 2
    assert len(ctrl.graph_ctrl.panels) == 2
    assert ctrl.graph_ctrl.panel_of(reloaded) is ctrl.graph_ctrl.panels[1]


def test_text_annotation_in_clicked_panel(ctrl, files, qapp):
    graph = ctrl.graph_ctrl
    ctrl.view.resize(1400, 900)
    ctrl.view.show()
    qapp.processEvents()
    sig = files[1].signals[1]
    _set_graph(ctrl, sig, 2)
    second = graph.panels[1]
    graph.highlight(sig)                            # texte prérempli : valeur du sinus
    qapp.processEvents()
    scene = second.vb.mapViewToScene(second.vb.viewRect().center())
    text = graph.add_text_annotation(scene)
    text.window.reject()
    assert text.plotItem is second.plot
    [annotation] = graph.graph_tree_ctrl.annotations()
    assert annotation.graph == 2
    # le texte garde son panneau quand la courbe le quitte
    _set_graph(ctrl, sig, 1)
    assert len(graph.panels) == 2


def test_mouse_cursor_moves_to_hovered_panel(ctrl, files, qapp):
    graph = ctrl.graph_ctrl
    cursor = graph.graph_tree_ctrl.mouseCursor
    cursor.param('show cursors').setValue(True)
    _set_graph(ctrl, files[1].signals[1], 2)
    second = graph.panels[1]
    graph._mouse_panel = second
    graph._mouse_pos = QtCore.QPointF(10, 20)
    graph._update_cursor(10.0, None)
    assert cursor.graph is second.plot
    assert cursor.cursors[0].getViewBox() is second.vb
    # panneau retiré : curseur ramené dans le panneau principal
    _set_graph(ctrl, files[1].signals[1], 1)
    assert cursor.graph is graph.plot


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


def test_text_annotation_panel_saved_and_removed(ctrl, files, tmp_path):
    graph = ctrl.graph_ctrl
    sig = files[1].signals[1]
    _set_graph(ctrl, sig, 2)
    graph.graph_tree_ctrl.addText(pos=(100, 20), text="note", edit=False, graph=2)
    _set_graph(ctrl, sig, 1)
    assert len(graph.panels) == 2                   # gardé pour le texte

    project = tmp_path / "text.json"
    ctrl.workspace.save(project)
    ctrl.import_ctrl.openProject(str(project))
    graph = ctrl.graph_ctrl
    [annotation] = graph.graph_tree_ctrl.annotations()
    assert annotation.graph == 2 and len(graph.panels) == 2
    assert graph.graph_tree_ctrl.textItems[annotation.id].plotItem is graph.panels[1].plot

    graph.graph_tree_ctrl.remove_annotation(annotation.id)
    assert len(graph.panels) == 1


# ---------------- « Graph » d'un fichier, d'un groupe : toutes leurs voies ----------------

def _set_container_graph(ctrl, obj, role, number):
    from ressources.custom_items import SelectionContext
    ctrl._on_param_changed(SelectionContext(role=role, signal=obj),
                           dict(obj.get_params(), graph_number=number))


def test_file_graph_number_applies_to_its_channels(ctrl, files):
    from ressources.custom_items import itemType
    graph = ctrl.graph_ctrl
    assert files[1].get_params()["graph_number"] == 1
    _set_container_graph(ctrl, files[1], itemType.FILE, 2)
    assert [s.graph_number for s in files[1].signals] == [2, 2]
    assert all(graph.panel_of(s) is graph.panels[1] for s in files[1].signals)
    assert all(graph.panel_of(s) is graph.main_panel for s in files[0].signals)
    assert files[1].graph_number == 2

    # la dernière affectation l'emporte : une voie seule, puis le fichier de nouveau
    _set_graph(ctrl, files[1].signals[0], 3)
    assert len(graph.panels) == 3
    _set_container_graph(ctrl, files[1], itemType.FILE, 1)
    assert [s.graph_number for s in files[1].signals] == [1, 1]
    assert len(graph.panels) == 1


def test_file_graph_number_keeps_other_file_params(ctrl, files):
    """Le reste des paramètres du fichier (période, libellé...) n'est pas touché."""
    from ressources.custom_items import itemType
    params = dict(files[0].get_params(), label="100 W")
    from ressources.custom_items import SelectionContext
    ctrl._on_param_changed(SelectionContext(role=itemType.FILE, signal=files[0]), params)
    assert files[0].label == "100 W"
    assert all(s.graph_number == 1 for s in files[0].signals)


def test_group_graph_number_applies_to_its_channels(ctrl, files, monkeypatch):
    from ressources.custom_items import itemType
    monkeypatch.setattr(ctrl, "_ask_group_name", lambda title, default: "Sinus")
    key = next(g.key for g in ctrl.channel_model.groups() if g.name == "CH2")
    ctrl.edit_channel_groups("new", [key])
    [group] = ctrl.workspace.channel_groups
    _set_container_graph(ctrl, group, itemType.CHANNEL_GROUP, 2)
    graph = ctrl.graph_ctrl
    assert [s.graph_number for s in group.signals] == [2, 2]
    assert all(graph.panel_of(f.signals[1]) is graph.panels[1] for f in files)
    assert all(graph.panel_of(f.signals[0]) is graph.main_panel for f in files)
    assert group.name == "Sinus"                    # pas renommé

    # voies du fichier A dans deux graphiques : « mixte » (0)
    assert files[0].graph_number == 0
    _set_container_graph(ctrl, files[0], itemType.FILE, 0)
    assert files[0].signals[1].graph_number == 2   # 0 : rien n'est appliqué
    # puis le fichier A dans le graphique 1 : sa voie CH2 quitte le graphique 2
    _set_container_graph(ctrl, files[0], itemType.FILE, 1)
    assert files[0].signals[1].graph_number == 1 and files[1].signals[1].graph_number == 2
