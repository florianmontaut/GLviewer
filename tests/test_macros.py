# tests/test_macros.py
"""Enregistrement et application des macros (WorkspaceController)."""
import pytest
from PyQt6 import QtWidgets

from ressources.custom_types import qSignalType as T, ActionModifier as M
from ressources.custom_exceptions import InvalidModelFit
from model.analysis.thermal import ThermalModelAnalysis
from helpers import add, load, nodes


@pytest.fixture
def macro_name(monkeypatch):
    """Réponse à la boîte de dialogue « Nom de la macro » (None = Annuler)."""
    answer = {"name": "ma_macro"}
    def fake_get_text(*args, **kw):
        name = answer["name"]
        return (name, True) if name is not None else ("", False)
    monkeypatch.setattr(QtWidgets.QInputDialog, "getText", fake_get_text)
    return answer


@pytest.fixture
def restart_answer(monkeypatch):
    """Réponse à la question « recommencer l'enregistrement ? »."""
    answer = {"button": QtWidgets.QMessageBox.StandardButton.Yes, "asked": 0}
    def fake_question(*args, **kw):
        answer["asked"] += 1
        return answer["button"]
    monkeypatch.setattr(QtWidgets.QMessageBox, "question", fake_question)
    return answer


def _menu(ctrl, action_type, sig):
    """Simule un clic dans le menu contextuel sur le signal sig."""
    ctrl.view.treefile.setCurrentIndex(ctrl.model.index_from_item(
                                        ctrl.model.find_signal_item(sig)))
    ctrl._action_concentrator(M.ADD_ACTION, action_type)


def _record(ctrl, sig, *requests):
    _menu(ctrl, T.START, sig)
    for request in requests:
        ctrl.workspace_ctrl.push(sig, request)
    _menu(ctrl, T.STOP, sig)


def _recording_flags(ctrl):
    return (ctrl.workspace_ctrl.is_recording,
            ctrl.tree_ctrl.macro_recording,
            ctrl.graph_ctrl.macro_recording)


def test_record_macro(ctrl, csv_files, macro_name):
    sig = load(ctrl, csv_files[0])[0].signals[0]

    _menu(ctrl, T.START, sig)
    assert _recording_flags(ctrl) == (True, True, True)
    ctrl.workspace_ctrl.push(sig, add(T.OFFSET, {"offset": 1.0}))
    ctrl.workspace_ctrl.push(sig, add(T.AVG, {"window": 3}))
    _menu(ctrl, T.STOP, sig)

    macro = ctrl.workspace_ctrl.macros["ma_macro"]
    assert [r.action_type for r in macro.action_requests] == [T.OFFSET, T.AVG]
    assert _recording_flags(ctrl) == (False, False, False)
    assert "ma_macro" in [a.text() for a in ctrl.tree_ctrl.menu.macro_menu.actions()]


def test_cancelled_name_keeps_recording(ctrl, csv_files, macro_name):
    sig = load(ctrl, csv_files[0])[0].signals[0]
    _menu(ctrl, T.START, sig)
    ctrl.workspace_ctrl.push(sig, add(T.OFFSET, {"offset": 1.0}))

    macro_name["name"] = None
    _menu(ctrl, T.STOP, sig)

    assert _recording_flags(ctrl) == (True, True, True)
    assert len(ctrl.workspace_ctrl._macro_buffer) == 1
    assert ctrl.workspace_ctrl.macros == {}


def test_failed_action_is_not_recorded(ctrl, csv_files, macro_name, monkeypatch):
    sig = load(ctrl, csv_files[0])[0].signals[0]
    def bad_fit(self, *args, **kw):
        raise InvalidModelFit("fit impossible")
    monkeypatch.setattr(ThermalModelAnalysis, "run", bad_fit)

    _record(ctrl, sig, add(T.OFFSET, {"offset": 1.0}), add(T.MODEL))

    macro = ctrl.workspace_ctrl.macros["ma_macro"]
    assert [r.action_type for r in macro.action_requests] == [T.OFFSET]


# ---------------- TODO : relancer un enregistrement en cours ----------------

def test_start_is_available_while_recording(ctrl, csv_files):
    sig = load(ctrl, csv_files[0])[0].signals[0]
    _menu(ctrl, T.START, sig)
    ctrl.tree_ctrl.checkStates(sig)

    actions = {a.text(): a.isEnabled() for a in ctrl.tree_ctrl.menu.macro_menu.actions()}
    assert actions["Start macro recording"] and actions["Stop macro recording"]


def test_restart_recording_resets_buffer(ctrl, csv_files, restart_answer, macro_name):
    sig = load(ctrl, csv_files[0])[0].signals[0]
    _menu(ctrl, T.START, sig)
    ctrl.workspace_ctrl.push(sig, add(T.OFFSET, {"offset": 1.0}))

    _menu(ctrl, T.START, sig)                     # « Oui, recommencer »
    assert restart_answer["asked"] == 1
    assert ctrl.workspace_ctrl._macro_buffer == []
    assert _recording_flags(ctrl) == (True, True, True)

    ctrl.workspace_ctrl.push(sig, add(T.AVG, {"window": 3}))
    _menu(ctrl, T.STOP, sig)
    macro = ctrl.workspace_ctrl.macros["ma_macro"]
    assert [r.action_type for r in macro.action_requests] == [T.AVG]
    # l'historique undo n'est pas touché : seul le buffer de la macro est remis à zéro
    assert ctrl.workspace_ctrl.undo_stack.count() == 2


def test_restart_recording_declined_keeps_buffer(ctrl, csv_files, restart_answer):
    sig = load(ctrl, csv_files[0])[0].signals[0]
    _menu(ctrl, T.START, sig)
    ctrl.workspace_ctrl.push(sig, add(T.OFFSET, {"offset": 1.0}))

    restart_answer["button"] = QtWidgets.QMessageBox.StandardButton.No
    _menu(ctrl, T.START, sig)

    assert len(ctrl.workspace_ctrl._macro_buffer) == 1
    assert ctrl.workspace_ctrl.is_recording


def test_empty_buffer_restart_does_not_ask(ctrl, csv_files, restart_answer):
    sig = load(ctrl, csv_files[0])[0].signals[0]
    _menu(ctrl, T.START, sig)
    _menu(ctrl, T.START, sig)
    assert restart_answer["asked"] == 0 and ctrl.workspace_ctrl.is_recording


# ---------------- application d'une macro ----------------

def test_apply_macro_on_other_signal_single_undo(ctrl, csv_files, macro_name):
    sig_a, sig_b = load(ctrl, csv_files[0])[0].signals
    _record(ctrl, sig_a, add(T.OFFSET, {"offset": 1.0}), add(T.AVG, {"window": 3}))
    count_before = ctrl.workspace_ctrl.undo_stack.count()

    ctrl.workspace_ctrl.apply_macro("ma_macro", sig_b)

    assert [n.action_type for n in nodes(sig_b.pipeline)] == [T.OFFSET, T.AVG]
    sig_item = ctrl.model.find_signal_item(sig_b)
    assert [c.obj for c in sig_item.children] == nodes(sig_b.pipeline)
    # une seule entrée dans l'historique pour toute la macro
    assert ctrl.workspace_ctrl.undo_stack.count() == count_before + 1
    ctrl.workspace_ctrl.undo_stack.undo()
    assert nodes(sig_b.pipeline) == [] and sig_item.children == []
    ctrl.workspace_ctrl.undo_stack.redo()
    assert [n.action_type for n in nodes(sig_b.pipeline)] == [T.OFFSET, T.AVG]


def test_apply_macro_with_modify_step(ctrl, csv_files, macro_name):
    """Chaque étape est construite sur l'état laissé par la précédente."""
    from helpers import make_request
    sig_a, sig_b = load(ctrl, csv_files[0])[0].signals
    _record(ctrl, sig_a, add(T.OFFSET, {"offset": 1.0}),
                         make_request(M.MODIFY_ACTION, T.OFFSET, {"offset": 5.0}, 0))

    ctrl.workspace_ctrl.apply_macro("ma_macro", sig_b)

    assert [n.get_param("offset") for n in nodes(sig_b.pipeline)] == [5.0]


def test_apply_macro_failure_rolls_back(ctrl, csv_files, macro_name, warnings_shown,
                                        monkeypatch):
    sig_a, sig_b = load(ctrl, csv_files[0])[0].signals
    _record(ctrl, sig_a, add(T.OFFSET, {"offset": 1.0}), add(T.MODEL))
    count_before = ctrl.workspace_ctrl.undo_stack.count()

    def bad_fit(self, *args, **kw):
        raise InvalidModelFit("fit impossible")
    monkeypatch.setattr(ThermalModelAnalysis, "run", bad_fit)
    ctrl.workspace_ctrl.apply_macro("ma_macro", sig_b)

    # rien ne reste de la macro partiellement appliquée
    assert nodes(sig_b.pipeline) == [] and len(sig_b.analyses) == 0
    assert ctrl.model.find_signal_item(sig_b).children == []
    assert ctrl.workspace_ctrl.undo_stack.count() == count_before
    assert len(warnings_shown) >= 1
