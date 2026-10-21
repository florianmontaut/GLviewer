# tests/test_pipeline.py
import numpy as np

from ressources.custom_types import qSignalType as T, ActionModifier as M
from helpers import add, make_request, load, nodes


def test_filters_keep_insertion_order(ctrl, csv_files):
    sig = load(ctrl, csv_files[0])[0].signals[0]
    for offset in (1.0, 2.0, 3.0):
        ctrl.workspace_ctrl.push(sig, add(T.OFFSET, {"offset": offset}))

    assert [n.get_param("offset") for n in nodes(sig.pipeline)] == [1.0, 2.0, 3.0]
    sig_item = ctrl.model.find_item(ctrl.model.root, sig)
    assert [c.obj for c in sig_item.children] == nodes(sig.pipeline)
    np.testing.assert_allclose(sig.y, sig.raw_y + 6.0)


def test_undo_redo_filters(ctrl, csv_files):
    sig = load(ctrl, csv_files[0])[0].signals[0]
    ctrl.workspace_ctrl.push(sig, add(T.OFFSET, {"offset": 1.0}))
    ctrl.workspace_ctrl.push(sig, add(T.OFFSET, {"offset": 2.0}))
    stack = ctrl.workspace_ctrl.undo_stack

    stack.undo()
    assert [n.get_param("offset") for n in nodes(sig.pipeline)] == [1.0]
    stack.redo()
    assert [n.get_param("offset") for n in nodes(sig.pipeline)] == [1.0, 2.0]
    stack.undo(); stack.undo()
    assert nodes(sig.pipeline) == []
    np.testing.assert_allclose(sig.y, sig.raw_y)


def test_modify_filter(ctrl, csv_files):
    sig = load(ctrl, csv_files[0])[0].signals[0]
    ctrl.workspace_ctrl.push(sig, add(T.OFFSET, {"offset": 1.0}))
    ctrl.workspace_ctrl.push(sig, make_request(M.MODIFY_ACTION, T.OFFSET, {"offset": 5.0}, 0))

    assert nodes(sig.pipeline)[0].get_param("offset") == 5.0
    ctrl.workspace_ctrl.undo_stack.undo()
    assert nodes(sig.pipeline)[0].get_param("offset") == 1.0


def test_moving_average_can_be_added(ctrl, csv_files):
    sig = load(ctrl, csv_files[0])[0].signals[0]
    ctrl.workspace_ctrl.push(sig, add(T.AVG, {"window": 5}))

    assert [n.action_type for n in nodes(sig.pipeline)] == [T.AVG]


def test_unknown_action_raises_clear_error(ctrl, csv_files):
    import pytest
    sig = load(ctrl, csv_files[0])[0].signals[0]
    with pytest.raises(KeyError, match="No action registered"):
        ctrl.workspace_ctrl.registry.execute(sig, add(T.RMS))
