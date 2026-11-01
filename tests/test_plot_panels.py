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


# ---------------- graphique actif : celui du dernier signal sélectionné ----------------

def _select(ctrl, sig):
    from ressources.custom_items import SelectionContext, itemType
    ctrl.select_from_context(SelectionContext(role=itemType.RAW, signal=sig), source="tree")


def test_active_panel_follows_selected_signal(ctrl, files):
    graph = ctrl.graph_ctrl
    tools = graph.graph_tree_ctrl
    tools.cursors_V.param('show cursors').setValue(True)
    _set_graph(ctrl, files[1].signals[1], 2)
    assert graph.active_panel is graph.main_panel

    _select(ctrl, files[1].signals[1])
    second = graph.panels[1]
    assert graph.active_panel is second
    assert tools.cursors_V.graph is second.plot and tools.cursors_H.graph is second.plot
    assert all(c.getViewBox() is second.vb for c in tools.cursors_V.cursors)

    # fichier sélectionné (pas de courbe) : le graphique actif ne change pas
    from ressources.custom_items import SelectionContext, itemType
    ctrl.select_from_context(SelectionContext(role=itemType.FILE, signal=files[0]),
                             source="tree")
    assert graph.active_panel is second

    _select(ctrl, files[0].signals[0])
    assert graph.active_panel is graph.main_panel
    assert all(c.getViewBox() is graph.main_panel.vb for c in tools.cursors_V.cursors)


def test_selected_curve_moved_takes_tools_along(ctrl, files):
    graph = ctrl.graph_ctrl
    sig = files[0].signals[0]
    _select(ctrl, sig)
    _set_graph(ctrl, sig, 2)
    assert graph.active_panel is graph.panels[1]
    assert graph.graph_tree_ctrl.cursors_V.graph is graph.panels[1].plot
    # graphique retiré : outils ramenés dans le graphique principal
    _set_graph(ctrl, sig, 1)
    assert len(graph.panels) == 1
    assert graph.graph_tree_ctrl.cursors_V.graph is graph.plot


def test_alignment_markers_in_active_panel(ctrl, files):
    from ressources.custom_types import qSignalType as T, ActionModifier as M
    graph = ctrl.graph_ctrl
    _set_graph(ctrl, files[1].signals[1], 2)
    _select(ctrl, files[1].signals[1])
    item = ctrl.model.find_item(ctrl.model.root, files[1])
    ctrl.view.treefile.setCurrentIndex(ctrl.model.index_from_item(item))
    ctrl._action_concentrator(M.ADD_ACTION, T.ALIGN)
    align = ctrl.alignment_ctrl
    assert align.active
    second = graph.panels[1]
    assert all(item.getViewBox() is second.vb for item in align._items)
    align.cancel()
    assert all(item.scene() is None for item in [align.handle, align.point_a, align.point_b])


# ---------------- glisser-déposer depuis les arbres ----------------

def _mime_ids(data):
    from model.base_objects import GRAPH_SIGNALS_MIME
    return bytes(data.data(GRAPH_SIGNALS_MIME)).decode().split(",")


def test_file_tree_drag_carries_signals(ctrl, files):
    model = ctrl.model
    sig_index = model.index_from_item(model.find_item(model.root, files[0].signals[1]))
    file_index = model.index_from_item(model.find_item(model.root, files[1]))
    assert model.flags(sig_index) & QtCore.Qt.ItemFlag.ItemIsDragEnabled
    assert model.flags(file_index) & QtCore.Qt.ItemFlag.ItemIsDragEnabled
    assert _mime_ids(model.mimeData([sig_index])) == [files[0].signals[1].id]
    assert _mime_ids(model.mimeData([file_index])) == [s.id for s in files[1].signals]
    assert ctrl.view.treefile.dragEnabled()


def test_channel_tree_drag_carries_signals(ctrl, files, monkeypatch):
    monkeypatch.setattr(ctrl, "_ask_group_name", lambda title, default: "Sinus")
    key = next(g.key for g in ctrl.channel_model.groups() if g.name == "CH2")
    ctrl.edit_channel_groups("new", [key])
    model = ctrl.channel_model
    group_index = model.index(0, 0)                 # groupe « Sinus » en tête
    assert model.index(0, 0).internalPointer().obj.name == "Sinus"
    assert model.flags(group_index) & QtCore.Qt.ItemFlag.ItemIsDragEnabled
    assert sorted(_mime_ids(model.mimeData([group_index]))) == \
           sorted(f.signals[1].id for f in files)
    channel_index = model.index(1, 0)               # voie logique CH1
    data = model.mimeData([channel_index])
    assert sorted(_mime_ids(data)) == sorted(f.signals[0].id for f in files)
    assert data.hasFormat(model.CHANNEL_MIME_TYPE)  # glisser dans l'arbre inchangé
    # un groupe ne se dépose pas dans l'arbre
    assert not model.canDropMimeData(model.mimeData([group_index]),
                                     QtCore.Qt.DropAction.LinkAction, -1, -1, channel_index)


def _drop(ctrl, qapp, signals, scene_pos, kind="Drop"):
    from PyQt6 import QtGui
    from model.base_objects import graph_signals_mime
    view = ctrl.graph_ctrl.graph
    pos = view.mapFromScene(scene_pos)
    data = graph_signals_mime(signals)
    # Qt ignore un déplacement ou un dépôt sans entrée préalable (comme un vrai glisser)
    enter = QtGui.QDragEnterEvent(pos, QtCore.Qt.DropAction.LinkAction, data,
                                  QtCore.Qt.MouseButton.LeftButton,
                                  QtCore.Qt.KeyboardModifier.NoModifier)
    qapp.sendEvent(view.viewport(), enter)
    if kind == "Drop":
        cls, pos = QtGui.QDropEvent, QtCore.QPointF(pos)
    else:
        cls = QtGui.QDragMoveEvent
    event = cls(pos, QtCore.Qt.DropAction.LinkAction, data, QtCore.Qt.MouseButton.LeftButton,
                QtCore.Qt.KeyboardModifier.NoModifier)
    qapp.sendEvent(view.viewport(), event)
    qapp.processEvents()
    return event


def test_drop_on_graph_and_below_last(ctrl, files, qapp):
    graph = ctrl.graph_ctrl
    ctrl.view.resize(1400, 900)
    ctrl.view.show()
    qapp.processEvents()
    _set_graph(ctrl, files[0].signals[0], 2)
    qapp.processEvents()

    # sous le dernier graphique : nouveau graphique (3)
    last = graph.panels[-1].plot.sceneBoundingRect()
    below = QtCore.QPointF(last.center().x(), last.bottom() + 5)
    assert graph.graph_number_at(below) == 3
    move = _drop(ctrl, qapp, files[1].signals, below, kind="Move")
    assert move.isAccepted() and graph._drop_frame.isVisible()
    event = _drop(ctrl, qapp, files[1].signals, below)
    assert event.isAccepted()
    assert [s.graph_number for s in files[1].signals] == [3, 3]
    assert len(graph.panels) == 3 and not graph._drop_frame.isVisible()

    # sur le graphique 1 (axe compris)
    qapp.processEvents()
    first = graph.main_panel.plot.sceneBoundingRect()
    _drop(ctrl, qapp, [files[1].signals[0]], QtCore.QPointF(first.left() + 5, first.center().y()))
    assert files[1].signals[0].graph_number == 1
    assert graph.panel_of(files[1].signals[0]) is graph.main_panel


def test_drop_ignores_other_data(ctrl, files, qapp):
    from PyQt6 import QtGui
    view = ctrl.graph_ctrl.graph
    data = QtCore.QMimeData()
    data.setText("texte")
    event = QtGui.QDropEvent(QtCore.QPointF(50, 50), QtCore.Qt.DropAction.LinkAction, data,
                             QtCore.Qt.MouseButton.LeftButton,
                             QtCore.Qt.KeyboardModifier.NoModifier)
    qapp.sendEvent(view.viewport(), event)
    assert all(s.graph_number == 1 for f in files for s in f.signals)


# ---------------- hauteur des graphiques ----------------

def _pixel_heights(graph, qapp):
    qapp.processEvents()
    return [panel.plot.sceneBoundingRect().height() for panel in graph.panels]


@pytest.fixture
def three_panels(ctrl, files, qapp):
    ctrl.view.resize(1400, 900)
    ctrl.view.show()
    _set_graph(ctrl, files[0].signals[1], 2)
    _set_graph(ctrl, files[1].signals[1], 3)
    qapp.processEvents()
    return ctrl.graph_ctrl


def test_splitter_between_panels(three_panels, qapp):
    graph = three_panels
    assert len(graph._splitters) == 2
    heights = _pixel_heights(graph, qapp)
    assert max(heights) - min(heights) < 3          # hauteurs égales par défaut
    for splitter in graph._splitters:
        rect = splitter.sceneBoundingRect()
        upper = graph.panels[splitter.index].plot.sceneBoundingRect()
        lower = graph.panels[splitter.index + 1].plot.sceneBoundingRect()
        assert upper.bottom() - 6 < rect.center().y() < lower.top() + 6


def test_drag_splitter_sets_heights(ctrl, three_panels, qapp):
    graph = three_panels
    emitted = []
    graph.heights_changed.connect(emitted.append)
    first = graph.panels[0].plot.sceneBoundingRect()
    graph.drag_splitter(0, first.top() + 1.5 * first.height())
    heights = _pixel_heights(graph, qapp)
    assert heights[0] == pytest.approx(1.5 * first.height(), rel=0.03)
    assert heights[1] == pytest.approx(0.5 * first.height(), rel=0.05)
    assert heights[2] == pytest.approx(first.height(), rel=0.03)  # 3e inchangé
    # limite : hauteur minimale du graphique du dessous
    graph.drag_splitter(0, first.top() + 5 * first.height())
    assert _pixel_heights(graph, qapp)[1] == pytest.approx(graph.MIN_PANEL_HEIGHT, abs=3)
    # poignées replacées sur la nouvelle limite
    assert abs(graph._splitters[0].sceneBoundingRect().center().y()
               - graph.panels[0].plot.sceneBoundingRect().bottom()) < 6

    # fin du glisser : hauteurs enregistrées avec le projet (projet modifié)
    graph._splitters[0].mouseReleaseEvent(None)
    assert emitted and ctrl.workspace.graph_heights == emitted[-1]
    assert ctrl.is_modified()


def test_double_click_resets_heights(ctrl, three_panels, qapp):
    graph = three_panels
    first = graph.panels[0].plot.sceneBoundingRect()
    graph.drag_splitter(0, first.top() + 1.5 * first.height())
    graph._splitters[0].mouseDoubleClickEvent(QtWidgets_event())
    heights = _pixel_heights(graph, qapp)
    assert max(heights) - min(heights) < 3
    assert ctrl.workspace.graph_heights == [1.0, 1.0, 1.0]


def QtWidgets_event():
    """Événement factice : seul accept() est appelé."""
    class _Event:
        def accept(self):
            pass
    return _Event()


def test_heights_saved_in_project(ctrl, three_panels, qapp, tmp_path):
    graph = three_panels
    first = graph.panels[0].plot.sceneBoundingRect()
    graph.drag_splitter(0, first.top() + 1.5 * first.height())
    graph._splitters[0].mouseReleaseEvent(None)
    saved = list(ctrl.workspace.graph_heights)

    project = tmp_path / "heights.json"
    ctrl.workspace.save(project)
    ctrl.import_ctrl.openProject(str(project))
    graph = ctrl.graph_ctrl
    assert ctrl.workspace.graph_heights == saved
    assert graph.heights() == pytest.approx(saved, abs=0.01)
    heights = _pixel_heights(graph, qapp)
    assert heights[0] / heights[2] == pytest.approx(saved[0] / saved[2], rel=0.03)


def test_removed_panel_removes_splitter(ctrl, three_panels, files, qapp):
    graph = three_panels
    _set_graph(ctrl, files[1].signals[1], 1)
    assert len(graph.panels) == 2 and len(graph._splitters) == 1
    heights = _pixel_heights(graph, qapp)
    assert max(heights) - min(heights) < 3


def test_mouse_drag_on_splitter(three_panels, qapp):
    """Le glisser sur la poignée règle les hauteurs (et ne déplace pas la vue)."""
    from PyQt6.QtTest import QTest
    graph = three_panels
    view = graph.graph
    before = _pixel_heights(graph, qapp)
    x_range = graph.main_panel.vb.viewRange()[0]
    start = view.mapFromScene(graph._splitters[0].sceneBoundingRect().center())
    end = start + QtCore.QPoint(0, 80)
    left = QtCore.Qt.MouseButton.LeftButton
    QTest.mousePress(view.viewport(), left, QtCore.Qt.KeyboardModifier.NoModifier, start)
    for step in range(1, 5):
        QTest.mouseMove(view.viewport(), start + QtCore.QPoint(0, 20 * step))
    QTest.mouseRelease(view.viewport(), left, QtCore.Qt.KeyboardModifier.NoModifier, end)
    after = _pixel_heights(graph, qapp)
    assert after[0] == pytest.approx(before[0] + 80, abs=4)
    assert graph.main_panel.vb.viewRange()[0] == pytest.approx(x_range)


# ---------------- annulation (Ctrl+Z) d'un changement de graphique ----------------

def _undo(ctrl):
    ctrl.workspace_ctrl.undo_stack.undo()


def _redo(ctrl):
    ctrl.workspace_ctrl.undo_stack.redo()


def test_undo_signal_graph_change(ctrl, files):
    graph = ctrl.graph_ctrl
    sig = files[0].signals[0]
    stack = ctrl.workspace_ctrl.undo_stack
    count = stack.count()
    _set_graph(ctrl, sig, 2)
    assert stack.count() == count + 1 and stack.undoText() == "Move to graph 2"
    _undo(ctrl)
    assert sig.graph_number == 1 and len(graph.panels) == 1
    assert graph.panel_of(sig) is graph.main_panel
    _redo(ctrl)
    assert sig.graph_number == 2 and graph.panel_of(sig) is graph.panels[1]


def test_other_signal_params_not_in_graph_command(ctrl, files):
    """Seul le graphique est annulable : modifier l'unité n'ajoute pas d'étape."""
    stack = ctrl.workspace_ctrl.undo_stack
    count = stack.count()
    _set_unit(ctrl, files[0].signals[0], "W")
    assert stack.count() == count


def test_undo_file_graph_change_restores_each_channel(ctrl, files):
    from ressources.custom_items import itemType
    graph = ctrl.graph_ctrl
    _set_graph(ctrl, files[0].signals[1], 3)
    _set_container_graph(ctrl, files[0], itemType.FILE, 2)
    assert [s.graph_number for s in files[0].signals] == [2, 2]
    _undo(ctrl)                                     # un seul Ctrl+Z pour le fichier
    assert [s.graph_number for s in files[0].signals] == [1, 3]
    assert len(graph.panels) == 3


def test_undo_group_graph_change(ctrl, files, monkeypatch):
    from ressources.custom_items import itemType
    monkeypatch.setattr(ctrl, "_ask_group_name", lambda title, default: "Sinus")
    key = next(g.key for g in ctrl.channel_model.groups() if g.name == "CH2")
    ctrl.edit_channel_groups("new", [key])
    [group] = ctrl.workspace.channel_groups
    _set_container_graph(ctrl, group, itemType.CHANNEL_GROUP, 2)
    assert [s.graph_number for s in group.signals] == [2, 2]
    _undo(ctrl)
    assert [s.graph_number for s in group.signals] == [1, 1]
    assert ctrl.workspace.channel_groups == [group]     # le groupe, lui, reste


def test_mixed_value_pushes_nothing(ctrl, files):
    from ressources.custom_items import itemType
    _set_graph(ctrl, files[0].signals[1], 2)
    stack = ctrl.workspace_ctrl.undo_stack
    count = stack.count()
    _set_container_graph(ctrl, files[0], itemType.FILE, 0)
    assert stack.count() == count


def test_undo_drop(ctrl, files):
    graph = ctrl.graph_ctrl
    graph.signals_dropped.emit([s.id for s in files[1].signals], 2)
    assert [s.graph_number for s in files[1].signals] == [2, 2]
    _undo(ctrl)
    assert [s.graph_number for s in files[1].signals] == [1, 1]
    assert len(graph.panels) == 1


def test_undo_updates_parameter_tree(ctrl, files, qapp):
    sig = files[0].signals[0]
    from ressources.custom_items import SelectionContext, itemType
    ctrl.select_from_context(SelectionContext(role=itemType.RAW, signal=sig), source="tree")
    ctrl.param_ctrl.param.child("Graph").setValue(2)
    qapp.processEvents()
    assert sig.graph_number == 2
    _undo(ctrl)
    qapp.processEvents()
    assert ctrl.param_ctrl.param.child("Graph").value() == 1


# ---------------- graphiques détachés ----------------

def _rows(graph):
    """Tracés de la fenêtre principale, ligne par ligne."""
    layout = graph.graph.ci
    return [layout.getItem(row, 0) for row in range(len(graph.panels) + 1)]


def test_detach_and_reattach_at_same_place(ctrl, three_panels, qapp):
    graph = three_panels
    p1, p2, p3 = graph.panels
    graph.detach_panel(p2)
    qapp.processEvents()
    window = p2.window
    assert window is not None and window.isVisible()
    assert window.view.ci.getItem(0, 0) is p2.plot
    assert _rows(graph)[:3] == [p1.plot, p3.plot, None]
    assert graph.attached_panels() == [p1, p3]
    assert len(graph._splitters) == 1
    assert p2.xp_axis.label.isVisible() and p3.xp_axis.label.isVisible()
    assert not p1.xp_axis.label.isVisible()
    assert p2.detach_action.text() == "Reattach graph"
    assert window.windowTitle().startswith("Graph 2")
    # le graphique détaché garde son numéro, ses courbes et l'axe des temps commun
    assert graph.number_of_panel(p2) == 2 and p2.curves
    assert p2.vb.linkedView(p2.vb.XAxis) is p1.vb

    # fermeture de la fenêtre : graphique réintégré à sa place (entre 1 et 3)
    window.close()
    qapp.processEvents()
    assert p2.window is None
    assert _rows(graph)[:3] == [p1.plot, p2.plot, p3.plot]
    assert len(graph._splitters) == 2
    assert p2.detach_action.text() == "Detach graph"
    heights = _pixel_heights(graph, qapp)
    assert max(heights) - min(heights) < 3


def test_detach_action_in_menu_toggles(ctrl, three_panels, qapp):
    graph = three_panels
    p3 = graph.panels[2]
    assert p3.detach_action in p3.vb.menu.actions()
    p3.detach_action.trigger()
    assert p3.window is not None
    p3.detach_action.trigger()                      # « Reattach graph »
    assert p3.window is None and _rows(graph)[2] is p3.plot


def test_detach_only_graph_shows_placeholder(ctrl, files, qapp):
    graph = ctrl.graph_ctrl
    ctrl.view.resize(1400, 900)
    ctrl.view.show()
    main = graph.main_panel
    graph.detach_panel(main)
    qapp.processEvents()
    assert graph.attached_panels() == []
    assert graph._placeholder is not None
    assert graph.graph.ci.getItem(0, 0) is graph._placeholder
    assert not graph._splitters
    # le graphique principal reste le graphique 1 (plot, vb, curves)
    assert graph.plot is main.plot and main.window.view.ci.getItem(0, 0) is main.plot
    graph.update_vbox()

    # dépôt dans la fenêtre principale vide : nouveau graphique
    last = graph.graph.ci.sceneBoundingRect().center()
    assert graph.graph_number_at(last) == 2
    graph.signals_dropped.emit([files[1].signals[0].id], 2)
    assert graph._placeholder is None and graph.attached_panels() == [graph.panels[1]]
    assert graph.graph.ci.getItem(0, 0) is graph.panels[1].plot

    # retour du graphique principal : au-dessus du graphique 2
    main.window.close()
    qapp.processEvents()
    assert _rows(graph)[:2] == [main.plot, graph.panels[1].plot]


def test_detached_panel_receives_curves_and_is_removed_when_empty(ctrl, three_panels, files,
                                                                  qapp):
    graph = three_panels
    p3 = graph.panels[2]
    graph.detach_panel(p3)
    window = p3.window
    _set_graph(ctrl, files[0].signals[0], 3)
    assert graph.panel_of(files[0].signals[0]) is p3
    # graphique 3 vidé : retiré, sa fenêtre fermée (sans réintégration)
    _set_graph(ctrl, files[0].signals[0], 1)
    _set_graph(ctrl, files[1].signals[1], 1)
    qapp.processEvents()
    from PyQt6 import sip
    assert len(graph.panels) == 2 and p3 not in graph.panels
    assert sip.isdeleted(window) or not window.isVisible()
    assert graph.attached_panels() == graph.panels


def test_mouse_and_text_in_detached_window(ctrl, three_panels, files, qapp):
    graph = three_panels
    p2 = graph.panels[1]
    graph.detach_panel(p2)
    p2.window.resize(900, 500)
    qapp.processEvents()
    scene = p2.window.view.scene()
    center = p2.vb.sceneBoundingRect().center()
    assert graph.panel_at(center, scene) is p2
    assert graph.panel_at(center) is not p2          # même point, fenêtre principale

    # survol : le curseur souris passe dans la fenêtre détachée
    graph._on_mouse_moved((center,), scene)
    assert graph._mouse_panel is p2

    # texte au clic droit dans la fenêtre détachée
    sig = files[0].signals[1]
    graph.highlight(sig)
    text = graph.add_text_annotation(center, scene)
    text.window.reject()
    assert text.plotItem is p2.plot
    [annotation] = graph.graph_tree_ctrl.annotations()
    assert annotation.graph == 2


def test_drop_in_detached_window(ctrl, three_panels, files, qapp):
    from PyQt6 import QtGui
    from model.base_objects import graph_signals_mime
    graph = three_panels
    p2 = graph.panels[1]
    graph.detach_panel(p2)
    qapp.processEvents()
    view = p2.window.view
    data = graph_signals_mime([files[0].signals[0]])
    pos = QtCore.QPoint(50, 50)
    args = (QtCore.Qt.DropAction.LinkAction, data, QtCore.Qt.MouseButton.LeftButton,
            QtCore.Qt.KeyboardModifier.NoModifier)
    qapp.sendEvent(view.viewport(), QtGui.QDragEnterEvent(pos, *args))
    qapp.sendEvent(view.viewport(), QtGui.QDropEvent(QtCore.QPointF(pos), *args))
    assert files[0].signals[0].graph_number == 2


def test_range_picker_in_detached_panel(ctrl, three_panels, files, qapp):
    graph = three_panels
    p2 = graph.panels[1]
    graph.detach_panel(p2)
    sig = files[0].signals[1]
    graph.start_range_selection(sig)
    assert graph.range_picker.region.getViewBox() is p2.vb
    graph.range_picker.cancel()


def test_main_window_close_reattaches(ctrl, three_panels, qapp):
    graph = three_panels
    p2 = graph.panels[1]
    graph.detach_panel(p2)
    window = p2.window
    ctrl.view.close()
    qapp.processEvents()
    from PyQt6 import sip
    assert p2.window is None and (sip.isdeleted(window) or not window.isVisible())


def test_theme_applied_to_detached_window(ctrl, three_panels, qapp):
    from ressources import theme
    graph = three_panels
    p2 = graph.panels[1]
    graph.detach_panel(p2)
    graph.updateOptions({"dark_mode": True})
    expected = pg_color(theme.graph_background(graph.opts["background_color"], True))
    assert p2.window.view.backgroundBrush().color().name() == expected


def pg_color(value):
    import pyqtgraph as pg
    return pg.mkColor(value).name()


def test_detached_panel_keeps_same_time_range(ctrl, three_panels, qapp):
    """Fenêtre détachée (autre position, autre largeur) : même plage de temps."""
    graph = three_panels
    p2 = graph.panels[1]
    graph.detach_panel(p2)
    p2.window.resize(600, 300)
    p2.window.move(0, 0)
    qapp.processEvents()
    graph.main_panel.vb.setXRange(100, 300, padding=0)
    qapp.processEvents()
    assert p2.vb.viewRange()[0] == pytest.approx([100, 300])
    # et inversement : zoom dans la fenêtre détachée
    p2.vb.setXRange(50, 150, padding=0)
    qapp.processEvents()
    assert graph.main_panel.vb.viewRange()[0] == pytest.approx([50, 150], abs=1)


def test_text_survives_reattach(ctrl, three_panels, files, qapp):
    """
    Texte avec flèche ajouté dans une fenêtre détachée, puis fenêtre fermée : le texte
    revient dans la fenêtre principale sans erreur au dessin (pyqtgraph se déconnectait
    de la scène de la fenêtre, déjà détruite).
    """
    from PyQt6 import sip
    graph = three_panels
    p2 = graph.panels[1]
    graph.detach_panel(p2)
    p2.window.resize(900, 500)
    qapp.processEvents()
    scene = p2.window.view.scene()
    graph.highlight(files[0].signals[1])
    text = graph.add_text_annotation(p2.vb.sceneBoundingRect().center(), scene)
    text.window.reject()
    p2.window.grab()                                # dessiné dans la fenêtre détachée
    assert text._lastScene is scene
    window = p2.window
    window.close()
    # fenêtre détruite (deleteLater) AVANT que le texte soit redessiné
    sip.delete(window)
    graph.graph.grab()                              # dessiné dans la fenêtre principale
    assert text.scene() is graph.graph.scene()
    assert text._lastScene is graph.graph.scene()


def test_cursor_labels_survive_detached_panel_removal(ctrl, three_panels, files, qapp):
    """
    Valeur du curseur souris affichée dans un graphique détaché, puis ce graphique vidé
    (retiré, fenêtre détruite) : pas d'erreur au dessin suivant.
    """
    from PyQt6 import sip
    graph = three_panels
    cursor = graph.graph_tree_ctrl.mouseCursor
    cursor.param('show cursors').setValue(True)
    cursor.param('show X value').setValue(True)
    p3 = graph.panels[2]
    graph.detach_panel(p3)
    window = p3.window
    window.resize(900, 500)
    qapp.processEvents()
    # souris dans la fenêtre détachée : curseur et valeur y sont dessinés
    graph._on_mouse_moved((p3.vb.sceneBoundingRect().center(),), window.view.scene())
    graph._update_cursor(100.0, None)
    window.grab()
    assert cursor.valtext._lastScene is window.view.scene()
    _set_graph(ctrl, files[1].signals[1], 1)        # graphique 3 vidé : retiré
    if not sip.isdeleted(window):
        sip.delete(window)
    graph._mouse_panel = graph.main_panel
    graph._update_cursor(100.0, None)
    graph.graph.grab()
    qapp.processEvents()
    assert cursor.valtext._lastScene is graph.graph.scene()
