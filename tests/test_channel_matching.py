# tests/test_channel_matching.py
"""
Vue « Par voie », appariement des voies entre fichiers : par nom ou par numéro de voie
(CH) du GL, choix au chargement du 2e fichier ou dans les options, associations à la main
(glisser-déposer, menu contextuel), undo et sauvegarde dans le projet.
"""
import json

import numpy as np
import pytest
from PyQt6 import QtCore, QtWidgets

from model.channels import group_channels, same_grouping
from helpers import load

N = 50


def write_gl(path, channels):
    """Export .csv GL820 minimal. channels : [(« CH3 », nom), ...] (numéros quelconques)."""
    n_cols = len(channels) + 5
    pad = lambda cells: ";".join(cells + [""] * (n_cols - len(cells)))
    lines = [pad(["Vendor", "GRAPHTEC Corporation"]), pad(["Model", "GL820"]),
             pad(["Sampling", "1s"]), pad(["Total data points", str(N)]),
             pad(["Trigger", "0"]), pad(["Trigger time", "09/11/2023", "09:55:40"]),
             pad(["CH", " Signal name", " Input", " Range", " Filter", " Span"])]
    for ch, name in channels:
        lines.append(pad([ch, name, "TEMP", "TC_K", "40", "180.000000", "0.000000", "degC"]))
    lines.append(pad(["Data"]))
    lines.append(pad(["No.", " Date&Time", " ms"] + [ch for ch, _ in channels]))
    lines.append(pad(["NO.", "Time", "ms"] + ["degC"] * len(channels)))
    for k in range(N):
        lines.append(pad([str(k + 1), "09/11/2023 09:55", "0"]
                         + [f"{20 + j + np.sin(k / 5):+.1f}" for j in range(len(channels))]))
    path.write_bytes(("\r\n".join(lines) + "\r\n").encode("latin-1"))
    return str(path).replace("\\", "/")


@pytest.fixture
def gl_paths(tmp_path):
    # même voies, câblées différemment d'un essai à l'autre (CH12 absent comme sur un GL réel)
    a = write_gl(tmp_path / "essai_100W.csv",
                 [("CH1", "T AMB"), ("CH2", "BOB PH1"), ("CH12", "FER PH1")])
    b = write_gl(tmp_path / "essai_200W.csv",
                 [("CH1", "T AMB"), ("CH2", "FER PH1"), ("CH13", "bob_ph1")])
    return a, b


@pytest.fixture
def asked(ctrl, monkeypatch):
    """Réponses à la question du 2e fichier (None : annulé) et nombre de questions."""
    state = {"answer": ("name", False), "count": 0}

    def ask():
        state["count"] += 1
        return state["answer"]
    monkeypatch.setattr(ctrl, "_ask_channel_matching", ask)
    return state


def _load_gl(ctrl, *paths):
    for path in paths:
        ctrl.import_ctrl.openGLCsvFiles(path)
    return list(ctrl.workspace.files)


def _groups(ctrl):
    return [(g.name, [s.file.name for s in g.signals]) for g in ctrl.channel_model.groups()]


def _sig(file_obj, name):
    return next(s for s in file_obj.signals if s.name == name)


# ---------------- numéros de voie ----------------

def test_gl_channel_ids_come_from_file(ctrl, gl_paths, asked):
    a, b = _load_gl(ctrl, *gl_paths)
    assert [s.channel_id for s in a.signals] == ["CH1", "CH2", "CH12"]
    assert [s.channel_id for s in b.signals] == ["CH1", "CH2", "CH13"]


def test_csv_channel_ids_are_column_positions(ctrl, csv_files):
    files = load(ctrl, *csv_files)
    assert [s.channel_id for s in files[0].signals] == ["CH1", "CH2"]


def test_grouping_by_name_and_by_channel(ctrl, gl_paths, asked):
    _load_gl(ctrl, *gl_paths)
    ws = ctrl.workspace
    by_name = [(g.name, len(g.signals)) for g in group_channels(ws, "name")]
    assert by_name == [("T AMB", 2), ("BOB PH1", 2), ("FER PH1", 2)]
    by_channel = [(g.name, len(g.signals)) for g in group_channels(ws, "channel")]
    assert by_channel == [("CH1 · T AMB", 2), ("CH2 · BOB PH1", 2),
                          ("CH12 · FER PH1", 1), ("CH13 · bob_ph1", 1)]
    assert not same_grouping(ws)


# ---------------- choix du mode ----------------

def test_question_at_second_file(ctrl, gl_paths, asked):
    ctrl.import_ctrl.openGLCsvFiles(gl_paths[0])
    assert asked["count"] == 0 and ctrl.workspace.channel_matching is None
    asked["answer"] = ("channel", False)
    ctrl.import_ctrl.openGLCsvFiles(gl_paths[1])
    assert asked["count"] == 1
    assert ctrl.workspace.channel_matching == "channel"
    assert _groups(ctrl)[1] == ("CH2 · BOB PH1", ["essai_100W", "essai_200W"])
    # instance dont le nom diffère de celui de la voie logique : nom affiché
    model = ctrl.channel_model
    assert model.data(model.index(1, 0, model.index(1, 0))) == "essai_200W (FER PH1)"


def test_no_question_when_both_modes_agree(ctrl, csv_files, asked):
    load(ctrl, *csv_files)
    assert asked["count"] == 0 and ctrl.workspace.channel_matching is None


def test_no_second_question(ctrl, gl_paths, asked, tmp_path):
    _load_gl(ctrl, *gl_paths)
    ctrl.import_ctrl.openGLCsvFiles(
        write_gl(tmp_path / "essai_300W.csv", [("CH5", "T AMB"), ("CH6", "BOB PH1")]))
    assert asked["count"] == 1


def test_cancel_keeps_matching_by_name(ctrl, gl_paths, asked):
    asked["answer"] = None
    _load_gl(ctrl, *gl_paths)
    assert ctrl.workspace.channel_matching == "name"
    assert [n for n, _ in _groups(ctrl)] == ["T AMB", "BOB PH1", "FER PH1"]


def test_remember_choice_updates_settings(ctrl, gl_paths, asked):
    asked["answer"] = ("channel", True)
    _load_gl(ctrl, *gl_paths)
    assert ctrl.settings["channel_matching"] == "By channel number (CH)"
    with open(ctrl.menu_ctrl.user_config) as f:
        assert json.load(f)["settings"]["channel_matching"] == "By channel number (CH)"


def test_setting_without_question(ctrl, gl_paths, asked):
    ctrl.settings["channel_matching"] = "By channel number (CH)"
    ctrl.import_ctrl.openGLCsvFiles(gl_paths[0])
    assert ctrl.workspace.channel_matching == "channel"
    ctrl.import_ctrl.openGLCsvFiles(gl_paths[1])
    assert asked["count"] == 0


def test_dialog_counts_common_channels(ctrl, gl_paths, asked, monkeypatch):
    from ressources import custom_dialogs
    _load_gl(ctrl, *gl_paths)
    seen = {}

    class Dialog(custom_dialogs.ChannelMatchingDialog):
        def exec(self):
            seen["name"], seen["channel"] = self.by_name.text(), self.by_channel.text()
            self.by_channel.setChecked(True)
            return QtWidgets.QDialog.DialogCode.Accepted
    monkeypatch.setattr("controller.main_controller.ChannelMatchingDialog", Dialog)
    # vraie méthode (celle de l'instance est remplacée par la fixture asked)
    assert type(ctrl)._ask_channel_matching(ctrl) == ("channel", False)
    assert "(3 voie(s)" in seen["name"] and "(2 voie(s)" in seen["channel"]


def test_switch_mode_from_view_and_undo(ctrl, gl_paths, asked):
    _load_gl(ctrl, *gl_paths)
    ctrl.set_channel_matching("channel")
    assert ctrl.workspace.channel_matching == "channel"
    assert len(_groups(ctrl)) == 4
    ctrl.workspace_ctrl.undo_stack.undo()
    assert ctrl.workspace.channel_matching == "name" and len(_groups(ctrl)) == 3


# ---------------- associations à la main ----------------

def test_manual_link_and_undo(ctrl, gl_paths, asked):
    asked["answer"] = ("channel", False)
    a, b = _load_gl(ctrl, *gl_paths)
    bob_b = _sig(b, "bob_ph1")
    group_bob = ctrl.channel_model.groups()[1]
    ctrl.link_channel(bob_b, group_bob.key)

    assert _groups(ctrl)[1] == ("CH2 · BOB PH1", ["essai_100W", "essai_200W", "essai_200W"])
    model = ctrl.channel_model
    index = model.signal_index(bob_b)
    assert model.data(index, QtCore.Qt.ItemDataRole.FontRole).italic()
    assert "Associée à la main" in model.data(index, QtCore.Qt.ItemDataRole.ToolTipRole)

    ctrl.workspace_ctrl.undo_stack.undo()
    assert len(_groups(ctrl)) == 4
    ctrl.workspace_ctrl.undo_stack.redo()
    assert bob_b in ctrl.channel_model.groups()[1].signals


def test_links_belong_to_their_mode(ctrl, gl_paths, asked):
    asked["answer"] = ("channel", False)
    a, b = _load_gl(ctrl, *gl_paths)
    ctrl.link_channel(_sig(b, "bob_ph1"), ctrl.channel_model.groups()[1].key)
    ctrl.set_channel_matching("name")
    assert not any(g.manual for g in ctrl.channel_model.groups())
    ctrl.set_channel_matching("channel")
    assert any(g.manual for g in ctrl.channel_model.groups())


def test_drag_and_drop(ctrl, gl_paths, asked, qapp):
    asked["answer"] = ("channel", False)
    a, b = _load_gl(ctrl, *gl_paths)
    model = ctrl.channel_model
    fer_b = _sig(b, "FER PH1")                     # CH2 de l'essai à 200 W
    data = model.mimeData([model.signal_index(fer_b)])
    target = model.index(2, 0)                     # CH12 · FER PH1
    assert model.canDropMimeData(data, QtCore.Qt.DropAction.LinkAction, -1, -1, target)
    assert model.dropMimeData(data, QtCore.Qt.DropAction.LinkAction, -1, -1, target)
    qapp.processEvents()                           # traité après le dépôt
    assert fer_b in model.groups()[2].signals
    assert not model.canDropMimeData(data, QtCore.Qt.DropAction.LinkAction, -1, -1,
                                     QtCore.QModelIndex())


def _find(menu, text):
    for action in menu.actions():
        if action.text() == text:
            return action
        if action.menu():
            found = _find(action.menu(), text)
            if found:
                return found
    return None


def _action(menu, text):
    action = _find(menu, text)
    if action is None:
        raise KeyError(text)
    return action


def test_context_menu(ctrl, gl_paths, asked):
    asked["answer"] = ("channel", False)
    a, b = _load_gl(ctrl, *gl_paths)
    model = ctrl.channel_model
    t_amb_b = _sig(b, "T AMB")

    menu = ctrl.channel_ctrl.context_menu(model.signal_index(t_amb_b))
    assert not _action(menu, "Rétablir l'association automatique").isEnabled()
    _action(menu, "Mettre à part").trigger()
    assert ("CH1 · T AMB (essai_200W)", ["essai_200W"]) in _groups(ctrl)

    menu = ctrl.channel_ctrl.context_menu(model.signal_index(t_amb_b))
    _action(menu, "Rétablir l'association automatique").trigger()
    assert _groups(ctrl)[0] == ("CH1 · T AMB", ["essai_100W", "essai_200W"])

    menu = ctrl.channel_ctrl.context_menu(model.signal_index(_sig(b, "bob_ph1")))
    _action(menu, "CH2 · BOB PH1").trigger()
    assert len(model.groups()[1].signals) == 3

    menu = ctrl.channel_ctrl.context_menu(QtCore.QModelIndex())
    assert _action(menu, "Apparier les voies par numéro (CH)").isChecked()
    _action(menu, "Apparier les voies par nom").trigger()
    assert ctrl.workspace.channel_matching == "name"


def test_project_keeps_matching(ctrl, gl_paths, asked, tmp_path):
    asked["answer"] = ("channel", False)
    a, b = _load_gl(ctrl, *gl_paths)
    ctrl.link_channel(_sig(b, "bob_ph1"), ctrl.channel_model.groups()[1].key)
    project = tmp_path / "project.json"
    ctrl.workspace.save(project)

    ctrl.import_ctrl.openProject(str(project))

    assert ctrl.workspace.channel_matching == "channel"
    assert _groups(ctrl)[1] == ("CH2 · BOB PH1", ["essai_100W", "essai_200W", "essai_200W"])
    assert asked["count"] == 1                     # pas de question au rechargement


def test_set_apart_channel_named_after_file_label(ctrl, gl_paths, asked, qapp):
    asked["answer"] = ("channel", False)
    a, b = _load_gl(ctrl, *gl_paths)
    ctrl.link_channel(_sig(b, "T AMB"), "solo:essai_200W/T AMB")
    assert "CH1 · T AMB (essai_200W)" in [n for n, _ in _groups(ctrl)]

    # étiquette renseignée dans le ParameterTree : elle remplace le nom du fichier
    item = ctrl.model.find_item(ctrl.model.root, b)
    ctrl.view.treefile.setCurrentIndex(ctrl.model.index_from_item(item))
    ctrl.param_ctrl.param.child("Label").setValue("200 W")
    qapp.processEvents()
    assert "CH1 · T AMB (200 W)" in [n for n, _ in _groups(ctrl)]

    # étiquette effacée : retour au nom du fichier
    ctrl.param_ctrl.param.child("Label").setValue("")
    qapp.processEvents()
    assert "CH1 · T AMB (essai_200W)" in [n for n, _ in _groups(ctrl)]
