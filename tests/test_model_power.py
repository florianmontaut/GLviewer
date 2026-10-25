# tests/test_model_power.py
"""
Puissance du modèle thermique (Rth = ΔT / P) : valeur saisie, ou voie du fichier
(« Power source », ex: voie calculée steps(time; ...)) moyennée sur la plage du modèle.
"""
import numpy as np
import pytest
from PyQt6 import QtCore

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
    first = _model(ctrl, sig, (0.0, 290.0), power_channel="P")
    second = _model(ctrl, sig, (310.0, 599.0), power_channel="P")

    assert first.results.power == 200.0 and second.results.power == 800.0
    assert first.results.R_th == pytest.approx(_rth(first.results))
    assert first.results.power_channel == "P"
    assert "⚠" not in power_text(first.results)


def test_fit_range_over_two_steps_is_flagged(ctrl, files, power):
    analysis = _model(ctrl, files[0].signals[0], (0.0, 599.0), power_channel="P")
    res = analysis.results
    assert 200.0 < res.power < 800.0
    assert (res.power_min, res.power_max) == (200.0, 800.0)
    assert "⚠" in power_text(res) and "paliers" in power_text(res)


def test_model_follows_power_table_changes(ctrl, files, power):
    sig = files[0].signals[0]
    analysis = _model(ctrl, sig, power_channel="P")
    stack = ctrl.workspace_ctrl.undo_stack

    stack.push(ModifyComputedChannelCommand(ctrl, power,
                                            {"formula": "steps(time; 0; 400; 300; 800)"}))
    assert analysis.results.power == 400.0
    assert sig.derived_signals[0].metadata["params"]["results"]["power"] == 400.0

    stack.undo()
    assert analysis.results.power == 200.0


def test_removed_power_channel_flags_the_model(ctrl, files, power):
    sig = files[0].signals[0]
    analysis = _model(ctrl, sig, power_channel="P")
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

    source.setValue("P")
    qapp.processEvents()

    analysis = nodes(sig.analyses)[0]
    assert analysis.get_param("power_channel") == "P"
    assert analysis.results.power == 200.0


def test_power_channel_saved_with_project(ctrl, files, power, tmp_path):
    _model(ctrl, files[0].signals[0], power_channel="P")
    project = tmp_path / "power.json"
    ctrl.workspace.save(project)

    ctrl.import_ctrl.openProject(str(project))

    analysis = nodes(ctrl.workspace.files[0].signals[0].analyses)[0]
    assert analysis.get_param("power_channel") == "P"
    assert analysis.error is None and analysis.results.power == 200.0


def test_tree_tooltip_shows_power(ctrl, files, power):
    analysis = _model(ctrl, files[0].signals[0], power_channel="P")
    index = ctrl.model.index_from_item(ctrl.model.find_item_by_object_id(analysis.id))
    tip = ctrl.model.data(index, QtCore.Qt.ItemDataRole.ToolTipRole)
    assert "« P »" in tip and "200 W" in tip
