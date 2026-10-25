# tests/test_model_power.py
"""
Puissance du modèle thermique (Rth = ΔT / P) : valeur saisie, ou voie du fichier
(« Power source », ex: voie calculée steps(time; ...)) moyennée sur la plage du modèle.
"""
import numpy as np
import pytest
from PyQt6 import QtCore, QtWidgets

from controller.commands.computed_channel import ModifyComputedChannelCommand
from helpers import add, nodes
from model.benchmark import power_text
from ressources.custom_items import SelectionContext, itemType
from ressources.custom_types import qSignalType as T
from test_computed_channels import channel, dialog, files  # noqa: F401 (fixtures)

PROFILE = "steps(time; 0; 200; 300; 800)"          # 200 W jusqu'à 300 s, puis 800 W


@pytest.fixture
def power(ctrl, files, dialog):
    """Voie de puissance « P » dans fileA (voie modélisée : CH1)."""
    return channel(ctrl, dialog, files[0], PROFILE, name="P", unit="W")


def _model(ctrl, sig, model_range=(0.0, 290.0), **params):
    ok = ctrl.workspace_ctrl.push(sig, add(T.MODEL, {"model_range": list(model_range),
                                                     **params}))
    return nodes(sig.analyses)[-1] if ok else None


def _rth(results):
    return (results.T_inf - results.T0) / results.power


def test_manual_power_by_default(ctrl, files):
    analysis = _model(ctrl, files[0].signals[0])
    assert analysis.get_param("power_channel") == ""
    res = analysis.results
    assert res.power == 100.0 and res.power_channel == ""
    assert res.R_th == pytest.approx(_rth(res))
    assert "valeur saisie" in power_text(res)


def test_power_from_channel_on_fit_range(ctrl, files, power):
    sig = files[0].signals[0]
    first = _model(ctrl, sig, (0.0, 290.0), power_channel=power.id)
    second = _model(ctrl, sig, (310.0, 599.0), power_channel=power.id)

    assert first.results.power == 200.0 and second.results.power == 800.0
    assert first.results.R_th == pytest.approx(_rth(first.results))
    assert first.results.power_channel == "P"
    assert "⚠" not in power_text(first.results)


def test_fit_range_over_two_steps_is_flagged(ctrl, files, power):
    analysis = _model(ctrl, files[0].signals[0], (0.0, 599.0), power_channel=power.id)
    res = analysis.results
    assert 200.0 < res.power < 800.0
    assert (res.power_min, res.power_max) == (200.0, 800.0)
    assert "⚠" in power_text(res) and "paliers" in power_text(res)


def test_model_follows_power_table_changes(ctrl, files, power):
    sig = files[0].signals[0]
    analysis = _model(ctrl, sig, power_channel=power.id)
    stack = ctrl.workspace_ctrl.undo_stack

    stack.push(ModifyComputedChannelCommand(ctrl, power,
                                            {"formula": "steps(time; 0; 400; 300; 800)"}))
    assert analysis.results.power == 400.0
    assert sig.derived_signals[0].metadata["params"]["results"]["power"] == 400.0

    stack.undo()
    assert analysis.results.power == 200.0


def test_removed_power_channel_flags_the_model(ctrl, files, power):
    sig = files[0].signals[0]
    analysis = _model(ctrl, sig, power_channel=power.id)
    item = ctrl.model.find_item(ctrl.model.root, power)
    ctrl.view.treefile.setCurrentIndex(ctrl.model.index_from_item(item))

    ctrl._action_concentrator(None, T.DEL)

    assert "introuvable" in analysis.error
    assert not sig.derived_signals
    ctrl.workspace_ctrl.undo_stack.undo()
    assert analysis.error is None and analysis.results.power == 200.0


def test_zero_power_is_refused(ctrl, files, dialog, warnings_shown):
    sig = files[0].signals[0]
    channel(ctrl, dialog, files[0], "steps(time; 0; 0)", name="Off")

    assert _model(ctrl, sig, power=0.0) is None
    assert _model(ctrl, sig, power_channel="Off") is None
    assert not sig.analyses
    assert all("Puissance nulle" in str(w) for w in warnings_shown)
    assert len(warnings_shown) == 2


def test_power_channel_without_values_on_range(ctrl, files, dialog, warnings_shown):
    """Table commençant après la plage du modèle : pas de puissance connue."""
    channel(ctrl, dialog, files[0], "steps(time; 400; 800)", name="Late")
    assert _model(ctrl, files[0].signals[0], power_channel="Late") is None
    assert "pas de valeur" in str(warnings_shown[0])


def test_power_source_in_parameter_tree(ctrl, files, power, qapp):
    sig = files[0].signals[0]
    analysis = _model(ctrl, sig)
    ctrl.param_ctrl.load_params(SelectionContext(role=itemType.ANALYSE, signal=sig,
                                                 analysis_id=analysis.id))
    source = ctrl.param_ctrl.param.child("Power source")
    limits = source.opts["limits"]
    assert limits["Manual value"] == ""
    assert {"CH2", "P"} <= set(limits) and "CH1" not in limits    # pas la voie modélisée
    assert limits["P"] == power.id                             # nom affiché, id enregistré

    source.setValue(power.id)
    qapp.processEvents()

    analysis = nodes(sig.analyses)[0]
    assert analysis.get_param("power_channel") == power.id
    assert analysis.results.power == 200.0
    assert analysis.results.power_channel == "P"


def test_power_channel_saved_with_project(ctrl, files, power, tmp_path):
    _model(ctrl, files[0].signals[0], power_channel=power.id)
    project = tmp_path / "power.json"
    ctrl.workspace.save(project)

    ctrl.import_ctrl.openProject(str(project))

    analysis = nodes(ctrl.workspace.files[0].signals[0].analyses)[0]
    reloaded = next(s for s in ctrl.workspace.files[0].signals if s.name == "P")
    assert reloaded.id == power.id                       # id des voies sauvegardé
    assert analysis.get_param("power_channel") == power.id
    assert analysis.error is None and analysis.results.power == 200.0


def test_renamed_power_channel_still_used(ctrl, files, power):
    sig = files[0].signals[0]
    analysis = _model(ctrl, sig, power_channel=power.id)

    ctrl.workspace_ctrl.undo_stack.push(ModifyComputedChannelCommand(ctrl, power,
                                                                     {"name": "P conv"}))

    assert analysis.error is None and analysis.results.power == 200.0
    assert analysis.results.power_channel == "P conv"                # nom à jour
    assert "« P conv »" in power_text(analysis.results)


def test_power_channel_by_name_from_older_projects(ctrl, files, power):
    """Projets enregistrés avant l'id : power_channel contient le nom de la voie."""
    analysis = _model(ctrl, files[0].signals[0], power_channel="P")
    assert analysis.error is None and analysis.results.power == 200.0


def test_tree_tooltip_shows_power(ctrl, files, power):
    analysis = _model(ctrl, files[0].signals[0], power_channel=power.id)
    index = ctrl.model.index_from_item(ctrl.model.find_item_by_object_id(analysis.id))
    tip = ctrl.model.data(index, QtCore.Qt.ItemDataRole.ToolTipRole)
    assert "« P »" in tip and "200 W" in tip


# ---------------- choix groupé (vue « Par voie ») ----------------

def _power_channels(ctrl, dialog, files, levels=(200, 400)):
    """Voie « P » (W) dans chaque essai : level W jusqu'à 300 s."""
    out = []
    for file_obj, level in zip(files, levels):
        out.append(channel(ctrl, dialog, file_obj, f"steps(time; 0; {level}; 300; 800)",
                           name="P", unit="W"))
    ctrl.channel_model.rebuild()
    return out


def _answer_power_dialog(monkeypatch, answer):
    """Réponse de la boîte PowerSourceDialog : dict de choice(), ou None (annulée)."""
    from ressources import custom_dialogs
    seen = {}
    default_choice = custom_dialogs.PowerSourceDialog.choice

    def fake_exec(self):
        seen["choices"] = [(self.channels.itemText(i), self.channels.itemData(i))
                           for i in range(self.channels.count())]
        seen["default"] = default_choice(self)
        if answer is None:
            return QtWidgets.QDialog.DialogCode.Rejected
        return QtWidgets.QDialog.DialogCode.Accepted
    monkeypatch.setattr(custom_dialogs.PowerSourceDialog, "exec", fake_exec)
    if answer is not None:
        monkeypatch.setattr(custom_dialogs.PowerSourceDialog, "choice",
                            lambda self: answer(seen) if callable(answer) else answer)
    return seen


def _group_models(ctrl, signals, model_range=(0.0, 290.0)):
    ctrl.apply_to_signals(signals, T.MODEL)
    if ctrl._pending_model_signals is not None:
        ctrl.graph_ctrl.range_picker.accepted.emit(signals[0], *model_range)


def test_group_models_use_each_file_power_channel(ctrl, files, dialog, monkeypatch):
    p_a, p_b = _power_channels(ctrl, dialog, files)
    seen = _answer_power_dialog(monkeypatch, lambda seen: seen["default"])
    ch1 = [f.signals[0] for f in files]

    _group_models(ctrl, ch1)

    # voie « P » proposée (unité W) et choisie par défaut, CH1 (modélisée) exclue
    labels = [label for label, _ in seen["choices"]]
    assert "P (2/2 essai(s))" in labels and not any(l.startswith("CH1") for l in labels)
    assert "channel_key" in seen["default"]
    (model_a,), (model_b,) = nodes(ch1[0].analyses), nodes(ch1[1].analyses)
    assert model_a.get_param("power_channel") == p_a.id
    assert model_b.get_param("power_channel") == p_b.id
    assert (model_a.results.power, model_b.results.power) == (200.0, 400.0)
    # une seule entrée d'historique
    ctrl.workspace_ctrl.undo_stack.undo()
    assert not ch1[0].analyses and not ch1[1].analyses


def test_group_models_with_manual_power(ctrl, files, dialog, monkeypatch):
    _power_channels(ctrl, dialog, files)
    _answer_power_dialog(monkeypatch, {"power": 250.0})
    ch1 = [f.signals[0] for f in files]

    _group_models(ctrl, ch1)

    for sig in ch1:
        (model,) = nodes(sig.analyses)
        assert model.get_param("power_channel") == ""
        assert model.results.power == 250.0


def test_group_models_missing_power_channel_reported(ctrl, files, dialog, monkeypatch,
                                                    warnings_shown):
    (p_a,) = _power_channels(ctrl, dialog, files[:1])         # « P » dans fileA seulement
    seen = _answer_power_dialog(monkeypatch, lambda seen: seen["default"])
    ch1 = [f.signals[0] for f in files]

    _group_models(ctrl, ch1)

    assert "P (1/2 essai(s))" in [label for label, _ in seen["choices"]]
    assert nodes(ch1[0].analyses)[0].get_param("power_channel") == p_a.id
    assert not ch1[1].analyses
    assert "pas de voie de puissance « P »" in str(warnings_shown[0])


def test_group_models_cancelled_power_dialog(ctrl, files, dialog, monkeypatch):
    _power_channels(ctrl, dialog, files)
    _answer_power_dialog(monkeypatch, None)
    ch1 = [f.signals[0] for f in files]

    ctrl.apply_to_signals(ch1, T.MODEL)

    assert ctrl._pending_model_signals is None
    assert not ctrl.graph_ctrl.range_picker.is_active


def test_group_models_without_candidate_channel(ctrl, files, dialogs_opened):
    """Aucune autre voie : pas de question, puissance saisie par défaut."""
    signals = [s for f in files for s in f.signals]           # toutes les voies

    _group_models(ctrl, signals, (0.0, 599.0))

    assert "PowerSourceDialog" not in dialogs_opened
    assert all(nodes(sig.analyses)[0].results.power == 100.0 for sig in signals)


def test_power_source_dialog_defaults(qapp):
    from ressources.custom_dialogs import PowerSourceDialog
    dialog = PowerSourceDialog([("P (2/2)", "name:p"), ("CH2 (2/2)", "name:ch2")])
    assert dialog.manual_mode.isChecked() and not dialog.channels.isEnabled()
    assert dialog.choice() == {"power": 100.0}
    dialog = PowerSourceDialog([("P (2/2)", "name:p"), ("CH2 (2/2)", "name:ch2")],
                               preferred="name:ch2")
    assert dialog.choice() == {"channel_key": "name:ch2"}
