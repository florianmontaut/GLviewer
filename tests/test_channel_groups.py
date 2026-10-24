# tests/test_channel_groups.py
"""
Vue « Par voie », étape 4 : groupes de voies créés par l'utilisateur et filtre / analyse
appliqué d'un coup à toutes les voies d'une sélection (voie logique, groupe), annulable
en un seul Ctrl+Z.
"""
import numpy as np
import pytest
from PyQt6 import QtCore

from ressources.custom_types import qSignalType as T, itemType
from helpers import load, nodes

Qt = QtCore.Qt


@pytest.fixture
def files(ctrl, csv_files):
    return list(load(ctrl, *csv_files))          # fileA, fileB : voies CH1 et CH2


@pytest.fixture
def names(ctrl, monkeypatch):
    """Noms saisis pour les groupes (None : annulé)."""
    answers = []
    monkeypatch.setattr(ctrl, "_ask_group_name",
                        lambda title, default: answers.pop(0) if answers else default)
    return answers


def _key(ctrl, name):
    return next(g.key for g in ctrl.channel_model.groups() if g.name == name)


def _top(ctrl):
    """Premier niveau de la vue : (nom affiché, [voies logiques si groupe])."""
    model = ctrl.channel_model
    out = []
    for row in range(model.rowCount()):
        index = model.index(row, 0)
        item = index.internalPointer()
        children = ([model.data(model.index(r, 0, index)) for r in range(model.rowCount(index))]
                    if item.obj.item_type == itemType.CHANNEL_GROUP else None)
        out.append((model.data(index), children))
    return out


def _undo(ctrl):
    ctrl.workspace_ctrl.undo_stack.undo()


# ---------------- groupes ----------------

def test_new_group_and_undo(ctrl, files, names):
    names.append("Thermique")
    ctrl.edit_channel_groups("new", [_key(ctrl, "CH1")])
    assert _top(ctrl) == [("Thermique (1 voie(s))", ["CH1 (2)"]), ("CH2 (2)", None)]
    _undo(ctrl)
    assert _top(ctrl) == [("CH1 (2)", None), ("CH2 (2)", None)]


def test_cancelled_name_creates_nothing(ctrl, files, names):
    names.append(None)
    ctrl.edit_channel_groups("new", [_key(ctrl, "CH1")])
    assert ctrl.workspace.channel_groups == []
    assert ctrl.workspace_ctrl.undo_stack.count() == 0


def test_add_remove_rename_delete(ctrl, files, names):
    k1, k2 = _key(ctrl, "CH1"), _key(ctrl, "CH2")
    names.extend(["G1", "G2"])
    ctrl.edit_channel_groups("new", [k1])
    ctrl.edit_channel_groups("new", [k2])
    g1, g2 = ctrl.workspace.channel_groups

    ctrl.edit_channel_groups("add", (g1.id, [k2]))          # CH2 quitte G2
    assert (g1.keys, g2.keys) == ([k1, k2], [])
    ctrl.edit_channel_groups("remove", [k1])
    assert g1.keys == [k2]

    names.append("Bobinages")
    ctrl.edit_channel_groups("rename", g1.id)
    assert _top(ctrl)[0] == ("Bobinages (1 voie(s))", ["CH2 (2)"])

    ctrl.edit_channel_groups("delete", g1.id)
    assert [g.name for g in ctrl.workspace.channel_groups] == ["G2"]
    for _ in range(4):
        _undo(ctrl)
    assert [(g.name, g.keys) for g in ctrl.workspace.channel_groups] == [("G1", [k1]),
                                                                         ("G2", [k2])]


def test_drag_channel_into_group_and_out(ctrl, files, names, qapp):
    names.append("G")
    ctrl.edit_channel_groups("new", [_key(ctrl, "CH1")])
    model = ctrl.channel_model
    ch2 = next(g for g in model.groups() if g.name == "CH2")
    data = model.mimeData([model.object_index(ch2)])
    group_index = model.index(0, 0)
    assert model.canDropMimeData(data, Qt.DropAction.LinkAction, -1, -1, group_index)
    model.dropMimeData(data, Qt.DropAction.LinkAction, -1, -1, group_index)
    qapp.processEvents()
    assert _top(ctrl) == [("G (2 voie(s))", ["CH1 (2)", "CH2 (2)"])]

    ch1 = next(g for g in model.groups() if g.name == "CH1")
    model.dropMimeData(model.mimeData([model.object_index(ch1)]),
                       Qt.DropAction.LinkAction, -1, -1, QtCore.QModelIndex())
    qapp.processEvents()
    assert _top(ctrl) == [("G (1 voie(s))", ["CH2 (2)"]), ("CH1 (2)", None)]


def test_group_checkbox_toggles_all(ctrl, files, names):
    ctrl.edit_channel_groups("new", [_key(ctrl, "CH1"), _key(ctrl, "CH2")])
    model = ctrl.channel_model
    model.setData(model.index(0, 0), Qt.CheckState.Unchecked.value,
                  Qt.ItemDataRole.CheckStateRole)
    assert not any(s.visible for f in files for s in f.signals)
    assert not any(ctrl.graph_ctrl.curves[s].isVisible() for f in files for s in f.signals)


def test_selection_inside_group(ctrl, files, names):
    ctrl.edit_channel_groups("new", [_key(ctrl, "CH1")])
    sig = files[1].signals[0]
    ctrl.view.treefile.setCurrentIndex(ctrl.model.signal_index(sig))
    tree, model = ctrl.view.treechannels, ctrl.channel_model
    assert tree.currentIndex().internalPointer().obj is sig
    assert tree.isExpanded(model.index(0, 0))                 # groupe déplié


def test_group_expansion_kept(ctrl, files, names):
    ctrl.edit_channel_groups("new", [_key(ctrl, "CH1")])
    ctrl.view.treechannels.expand(ctrl.channel_model.index(0, 0))
    names.append("Renommé")
    ctrl.edit_channel_groups("rename", ctrl.workspace.channel_groups[0].id)
    assert ctrl.view.treechannels.isExpanded(ctrl.channel_model.index(0, 0))


# ---------------- actions sur toutes les voies ----------------

def test_offset_on_group_one_undo(ctrl, files, names, monkeypatch):
    monkeypatch.setattr(ctrl, "_ask_group_value", lambda action_type: 2.5)
    files[1].signals[1].visible = False                       # voie décochée : ignorée
    ctrl.edit_channel_groups("new", [_key(ctrl, "CH1"), _key(ctrl, "CH2")])
    signals = [s for f in files for s in f.signals if s.visible]

    ctrl.apply_to_signals(signals, T.OFFSET)

    for sig in signals:
        assert [n.get_param("offset") for n in nodes(sig.pipeline)] == [2.5]
        np.testing.assert_allclose(sig.y, sig.raw_y + 2.5)
    assert nodes(files[1].signals[1].pipeline) == []
    _undo(ctrl)                                               # un seul Ctrl+Z
    assert all(nodes(sig.pipeline) == [] for sig in signals)


def test_x_offset_on_channel(ctrl, files, monkeypatch):
    monkeypatch.setattr(ctrl, "_ask_group_value", lambda action_type: 10.0)
    ch1 = [f.signals[0] for f in files]
    ctrl.apply_to_signals(ch1, T.OFFSET_X)
    for sig in ch1:
        np.testing.assert_allclose(sig.x, sig.raw_x + 10.0)


def test_cancelled_value_does_nothing(ctrl, files, monkeypatch):
    monkeypatch.setattr(ctrl, "_ask_group_value", lambda action_type: None)
    ctrl.apply_to_signals([f.signals[0] for f in files], T.OFFSET)
    assert ctrl.workspace_ctrl.undo_stack.count() == 0


def test_filter_on_channel(ctrl, files):
    ch1 = [f.signals[0] for f in files]
    ctrl.apply_to_signals(ch1, T.FILTER)
    assert all([n.action_type for n in nodes(s.pipeline)] == [T.FILTER] for s in ch1)


def test_temperature_rise_uses_reference_of_same_file(ctrl, files):
    """« T AMB » de chaque essai : CH2 de fileA est la référence, CH2 de fileB sert à fileB."""
    ctrl.workspace.set_reference_signal(files[0].signals[1])
    ch1 = [f.signals[0] for f in files]
    ctrl.apply_to_signals(ch1, T.DIFF)
    for file_obj in files:
        sig, ref = file_obj.signals
        (node,) = nodes(sig.pipeline)
        assert node.action_type == T.DIFF and node.get_param("reference") is ref
        np.testing.assert_allclose(sig.y, sig.raw_y - ref.raw_y)


def test_temperature_rise_skips_reference_itself(ctrl, files):
    ctrl.workspace.set_reference_signal(files[0].signals[1])
    ctrl.apply_to_signals([f.signals[1] for f in files], T.DIFF)
    assert nodes(files[0].signals[1].pipeline) == []
    assert nodes(files[1].signals[1].pipeline) == []
    assert ctrl.workspace_ctrl.undo_stack.count() == 0         # rien appliqué : pas d'entrée


def test_thermal_model_on_channel_with_one_range(ctrl, files):
    ch1 = [f.signals[0] for f in files]
    ctrl.apply_to_signals(ch1, T.MODEL)
    ctrl.graph_ctrl.range_picker.accepted.emit(ch1[0], 0.0, 599.0)

    for sig in ch1:
        (analysis,) = nodes(sig.analyses)
        assert analysis.action_type == T.MODEL
        assert list(analysis.get_param("model_range")) == [0.0, 599.0]
    _undo(ctrl)
    assert all(nodes(sig.analyses) == [] for sig in ch1)


def test_range_cancel_forgets_group(ctrl, files):
    ch1 = [f.signals[0] for f in files]
    ctrl.apply_to_signals(ch1, T.MODEL)
    ctrl.graph_ctrl.range_picker.cancelled.emit(ch1[0])
    assert ctrl._pending_model_signals is None


def test_failures_reported_once(ctrl, files, warnings_shown):
    from ressources.custom_items import ActionRequest
    from ressources.custom_types import ActionModifier

    def build(sig):
        # plage vide pour fileB : le modèle ne peut pas être calculé
        rng = [0.0, 599.0] if sig.file is files[0] else [700.0, 800.0]
        return ActionRequest(action_modifier=ActionModifier.ADD_ACTION, action_type=T.MODEL,
                             params={"model_range": rng}, index=None)
    ctrl._push_group([f.signals[0] for f in files], build, T.MODEL)
    assert len(nodes(files[0].signals[0].analyses)) == 1
    assert nodes(files[1].signals[0].analyses) == []
    assert len(warnings_shown) == 1 and "1 en échec" in str(warnings_shown[0])


# ---------------- menu contextuel ----------------

def _texts(menu):
    out = []
    for action in menu.actions():
        out.append(action.text())
        if action.menu():
            out += ["  " + t for t in _texts(action.menu())]
    return out


def _action(menu, text):
    for action in menu.actions():
        if action.text() == text:
            return action
        if action.menu():
            for sub in action.menu().actions():
                if sub.text() == text:
                    return sub
    raise KeyError(text)


def test_context_menu_on_channel(ctrl, files, names, monkeypatch):
    model = ctrl.channel_model
    menu = ctrl.channel_ctrl.context_menu(model.index(0, 0))
    texts = _texts(menu)
    assert "Appliquer aux voies affichées (2)" in texts
    assert not _action(menu, "Get temperature rise").isEnabled()     # pas de référence
    assert not _action(menu, "Retirer du groupe").isEnabled()

    applied = []
    monkeypatch.setattr(ctrl, "apply_to_signals", lambda s, t: applied.append((s, t)))
    ctrl.channel_ctrl.apply_requested.disconnect()
    ctrl.channel_ctrl.apply_requested.connect(ctrl.apply_to_signals)
    _action(menu, "Filter selection").trigger()
    assert applied == [([f.signals[0] for f in files], T.FILTER)]

    names.append("G")
    _action(menu, "Nouveau groupe avec ces voies…").trigger()
    assert _top(ctrl)[0] == ("G (1 voie(s))", ["CH1 (2)"])


def test_context_menu_on_group(ctrl, files, names):
    ctrl.edit_channel_groups("new", [_key(ctrl, "CH1")])
    menu = ctrl.channel_ctrl.context_menu(ctrl.channel_model.index(0, 0))
    assert "Appliquer aux voies affichées (2)" in _texts(menu)
    _action(menu, "Supprimer le groupe").trigger()
    assert ctrl.workspace.channel_groups == []


def test_multi_selection(ctrl, files):
    tree, model = ctrl.view.treechannels, ctrl.channel_model
    sel = tree.selectionModel()
    for row in (0, 1):
        sel.select(model.index(row, 0), QtCore.QItemSelectionModel.SelectionFlag.Select
                                         | QtCore.QItemSelectionModel.SelectionFlag.Rows)
    menu = ctrl.channel_ctrl.context_menu(model.index(1, 0))
    assert "Appliquer aux voies affichées (4)" in _texts(menu)


# ---------------- sauvegarde ----------------

def test_project_keeps_groups(ctrl, files, names, tmp_path):
    names.append("Thermique")
    ctrl.edit_channel_groups("new", [_key(ctrl, "CH2")])
    project = tmp_path / "project.json"
    ctrl.workspace.save(project)
    ctrl.import_ctrl.openProject(str(project))
    assert _top(ctrl) == [("Thermique (1 voie(s))", ["CH2 (2)"]), ("CH1 (2)", None)]
