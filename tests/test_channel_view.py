# tests/test_channel_view.py
"""Vue « Par voie » : même voie dans plusieurs fichiers (ex: essais à 100, 200, 300 W)."""
import numpy as np
import pytest
from PyQt6 import QtCore, QtWidgets

from model.channels import channel_key, group_channels
from ressources.custom_types import qSignalType as T, ActionModifier as M
from helpers import add, load

Qt = QtCore.Qt


@pytest.fixture
def files(ctrl, csv_files):
    return list(load(ctrl, *csv_files))          # fileA, fileB : voies CH1 et CH2


def _rows(ctrl):
    model = ctrl.channel_model
    out = []
    for row in range(model.rowCount()):
        group_index = model.index(row, 0)
        children = [model.data(model.index(r, 0, group_index))
                    for r in range(model.rowCount(group_index))]
        out.append((model.data(group_index), children))
    return out


def _group_index(ctrl, name):
    model = ctrl.channel_model
    for row, group in enumerate(model.groups()):
        if group.name == name:
            return model.index(row, 0)
    raise KeyError(name)


def _check_state(model, index):
    return model.data(index, Qt.ItemDataRole.CheckStateRole)


# ---------------- appariement ----------------

@pytest.mark.parametrize("a, b", [("T_dissipateur", "t dissipateur"),
                                  ("T  Dissipateur", "T_DISSIPATEUR"),
                                  (" CH1 ", "ch1")])
def test_channel_key_matches_variants(a, b):
    assert channel_key(a) == channel_key(b)


def test_channel_key_keeps_different_channels_apart():
    assert channel_key("CH1") != channel_key("CH10")


def test_groups_across_files(ctrl, files):
    groups = group_channels(ctrl.workspace)
    assert [g.name for g in groups] == ["CH1", "CH2"]
    assert [[s.file.name for s in g.signals] for g in groups] == [["fileA", "fileB"]] * 2


def test_channel_present_in_one_file_only(ctrl, files, tmp_path):
    from conftest import _write_xy_csv
    path = tmp_path / "autre.csv"
    _write_xy_csv(path, 50, np.ones(50), np.ones(50))
    text = path.read_text().replace("CH2", "Pression")
    path.write_text(text)
    load(ctrl, str(path).replace("\\", "/"))
    assert [(g.name, len(g.signals)) for g in group_channels(ctrl.workspace)] == \
           [("CH1", 3), ("CH2", 2), ("Pression", 1)]


# ---------------- affichage ----------------

def test_tabs_and_tree(ctrl, files):
    tabs = ctrl.view.tree_tabs
    assert [tabs.tabText(i) for i in range(tabs.count())] == ["Par fichier", "Par voie"]
    assert ctrl.view.treechannels.model() is ctrl.channel_model
    assert _rows(ctrl) == [("CH1 (2)", ["fileA", "fileB"]), ("CH2 (2)", ["fileA", "fileB"])]


def test_tree_tabs_visible_at_startup(ctrl, qapp, csv_files):
    """L'arborescence ne doit pas s'ouvrir repliée (0 px) dans le splitter."""
    tabs = ctrl.view.tree_tabs
    splitter = tabs.parentWidget()
    ctrl.view.resize(1400, 900)
    ctrl.view.show()
    qapp.processEvents()
    assert tabs.width() >= tabs.minimumWidth() >= 200
    assert not splitter.isCollapsible(splitter.indexOf(tabs))

    load(ctrl, *csv_files)
    qapp.processEvents()
    assert tabs.width() >= 200
    ctrl.view.hide()


def test_instances_show_file_label(ctrl, files, qapp):
    files[0].set_params({"label": "100 W / 55 °C"})
    ctrl.channel_model.rebuild()
    assert _rows(ctrl)[0] == ("CH1 (2)", ["100 W / 55 °C", "fileB"])


def test_label_change_from_parameter_tree_updates_view(ctrl, files, qapp):
    item = ctrl.model.find_item(ctrl.model.root, files[1])
    ctrl.view.treefile.setCurrentIndex(ctrl.model.index_from_item(item))
    ctrl.param_ctrl.param.child("Label").setValue("200 W")
    qapp.processEvents()
    assert _rows(ctrl)[1] == ("CH2 (2)", ["fileA", "200 W"])


# ---------------- visibilité ----------------

def test_channel_checkbox_toggles_all_files(ctrl, files):
    model = ctrl.channel_model
    index = _group_index(ctrl, "CH1")
    sigs = [f.signals[0] for f in files]

    model.setData(index, Qt.CheckState.Unchecked.value, Qt.ItemDataRole.CheckStateRole)

    assert not any(s.visible for s in sigs)
    assert not any(ctrl.graph_ctrl.curves[s].isVisible() for s in sigs)
    for s in sigs:                                  # arbre « Par fichier » à jour
        state = ctrl.model.data(ctrl.model.signal_index(s), Qt.ItemDataRole.CheckStateRole)
        assert state == Qt.CheckState.Unchecked
    assert files[0].signals[1].visible               # CH2 non touchée

    model.setData(index, Qt.CheckState.Checked.value, Qt.ItemDataRole.CheckStateRole)
    assert all(ctrl.graph_ctrl.curves[s].isVisible() for s in sigs)


def test_partial_state(ctrl, files):
    model = ctrl.channel_model
    index = _group_index(ctrl, "CH1")
    instance = model.index(1, 0, index)             # CH1 de fileB
    model.setData(instance, Qt.CheckState.Unchecked.value, Qt.ItemDataRole.CheckStateRole)

    assert not files[1].signals[0].visible and files[0].signals[0].visible
    assert _check_state(model, index) == Qt.CheckState.PartiallyChecked


def test_file_tree_checkbox_updates_channel_view(ctrl, files):
    sig = files[0].signals[0]
    ctrl.model.setData(ctrl.model.signal_index(sig), Qt.CheckState.Unchecked.value,
                       Qt.ItemDataRole.CheckStateRole)
    assert _check_state(ctrl.channel_model, _group_index(ctrl, "CH1")) == \
           Qt.CheckState.PartiallyChecked


# ---------------- sélection synchronisée ----------------

def _current(tree):
    index = tree.currentIndex()
    return index.internalPointer().obj if index.isValid() else None


def test_selecting_instance_selects_signal_everywhere(ctrl, files):
    sig = files[1].signals[0]
    ctrl.view.treechannels.setCurrentIndex(ctrl.channel_model.signal_index(sig))

    assert _current(ctrl.view.treefile) is sig
    assert ctrl.graph_ctrl.old_highlight is sig
    assert ctrl.param_ctrl.param.child("Curve name").value() == sig.name


def test_selecting_in_file_tree_selects_instance(ctrl, files):
    sig = files[1].signals[1]
    ctrl.view.treefile.setCurrentIndex(ctrl.model.signal_index(sig))
    assert _current(ctrl.view.treechannels) is sig
    assert ctrl.view.treechannels.isExpanded(ctrl.channel_model.signal_index(sig).parent())


def test_selecting_filter_selects_parent_instance(ctrl, files):
    sig = files[0].signals[0]
    ctrl.workspace_ctrl.push(sig, add(T.OFFSET, {"offset": 1.0}))
    assert _current(ctrl.view.treechannels) is sig


def test_selecting_file_clears_channel_selection(ctrl, files):
    ctrl.view.treefile.setCurrentIndex(ctrl.model.signal_index(files[0].signals[0]))
    item = ctrl.model.find_item(ctrl.model.root, files[1])
    ctrl.view.treefile.setCurrentIndex(ctrl.model.index_from_item(item))
    assert not ctrl.view.treechannels.selectionModel().hasSelection()


def test_selecting_channel_row_does_nothing(ctrl, files):
    ctrl.view.treechannels.setCurrentIndex(_group_index(ctrl, "CH2"))
    assert ctrl.graph_ctrl.old_highlight is None


# ---------------- valeur au curseur ----------------

def test_cursor_value_column(ctrl, files):
    ctrl._on_cursor_moved(300.0)
    model = ctrl.channel_model
    group = _group_index(ctrl, "CH1")
    for row, file_obj in enumerate(files):
        sig = file_obj.signals[0]
        shown = model.data(model.index(row, 1, group))
        assert shown == f"{sig.nearest_value(300.0):.2f}{sig.unit}"


# ---------------- reconstruction ----------------

def test_remove_and_undo_file(ctrl, files, monkeypatch):
    monkeypatch.setattr(QtWidgets.QMessageBox, "question",
                        lambda *a, **k: QtWidgets.QMessageBox.StandardButton.Yes)
    ctrl.view.treechannels.expand(_group_index(ctrl, "CH1"))
    item = ctrl.model.find_item(ctrl.model.root, files[0])
    ctrl.view.treefile.setCurrentIndex(ctrl.model.index_from_item(item))
    ctrl._action_concentrator(M.ADD_ACTION, T.DEL)

    assert _rows(ctrl) == [("CH1 (1)", ["fileB"]), ("CH2 (1)", ["fileB"])]
    assert ctrl.view.treechannels.isExpanded(_group_index(ctrl, "CH1"))   # dépliage gardé

    ctrl.workspace_ctrl.undo_stack.undo()
    assert _rows(ctrl) == [("CH1 (2)", ["fileA", "fileB"]), ("CH2 (2)", ["fileA", "fileB"])]


def test_project_reload(ctrl, files, tmp_path):
    files[0].set_params({"label": "100 W"})
    project = tmp_path / "project.json"
    ctrl.workspace.save(project)

    ctrl.import_ctrl.openProject(str(project))

    assert ctrl.channel_model.workspace is ctrl.workspace
    assert _rows(ctrl)[0] == ("CH1 (2)", ["100 W", "fileB"])
    reloaded = ctrl.workspace.files[0].signals[0]
    assert ctrl.channel_model.signal_index(reloaded).isValid()
