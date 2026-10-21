# tests/test_node_ids.py
"""Identification des filtres / analyses par id (OrderedDict id -> node)."""
import numpy as np

from ressources.custom_types import qSignalType as T, ActionModifier as M
from helpers import add, make_request, load, nodes


def _tree_children(ctrl, sig):
    sig_item = ctrl.model.find_signal_item(sig)
    return [child.obj for child in sig_item.children]


def _derived_curves(ctrl, sig):
    return [s for s in ctrl.graph_ctrl.curves
            if s.item_type.name == "DERIVED" and s.parent_signal is sig]


def test_keys_match_node_ids(ctrl, csv_files):
    sig = load(ctrl, csv_files[0])[0].signals[0]
    ctrl.workspace_ctrl.push(sig, add(T.OFFSET, {"offset": 1.0}))
    ctrl.workspace_ctrl.push(sig, add(T.MODEL))

    assert all(key == node.id for key, node in sig.pipeline.items())
    assert all(key == node.id for key, node in sig.analyses.items())


def test_tree_order_filters_then_analyses(ctrl, csv_files):
    sig = load(ctrl, csv_files[0])[0].signals[0]
    ctrl.workspace_ctrl.push(sig, add(T.MODEL))
    ctrl.workspace_ctrl.push(sig, add(T.OFFSET, {"offset": 1.0}))
    ctrl.workspace_ctrl.push(sig, add(T.OFFSET, {"offset": 2.0}))

    assert _tree_children(ctrl, sig) == nodes(sig.pipeline) + nodes(sig.analyses)


def test_modify_analysis_does_not_overwrite_filter(ctrl, csv_files):
    sig = load(ctrl, csv_files[0])[0].signals[0]
    ctrl.workspace_ctrl.push(sig, add(T.OFFSET, {"offset": 1.0}))
    ctrl.workspace_ctrl.push(sig, add(T.MODEL))
    ctrl.workspace_ctrl.push(sig, make_request(M.MODIFY_ACTION, T.MODEL, {"power": 50.0}, 0))

    children = _tree_children(ctrl, sig)
    assert children[0] is nodes(sig.pipeline)[0]
    assert children[1] is nodes(sig.analyses)[0]
    assert children[1].get_param("power") == 50.0


def test_remove_filter_and_undo(ctrl, csv_files):
    sig = load(ctrl, csv_files[0])[0].signals[0]
    for offset in (1.0, 2.0, 3.0):
        ctrl.workspace_ctrl.push(sig, add(T.OFFSET, {"offset": offset}))
    middle = nodes(sig.pipeline)[1]

    ctrl.workspace_ctrl.push(sig, make_request(M.REMOVE_ACTION, T.OFFSET, index=1))
    assert [n.get_param("offset") for n in nodes(sig.pipeline)] == [1.0, 3.0]
    assert _tree_children(ctrl, sig) == nodes(sig.pipeline)

    ctrl.workspace_ctrl.undo_stack.undo()
    assert nodes(sig.pipeline)[1] is middle
    assert _tree_children(ctrl, sig) == nodes(sig.pipeline)


def test_remove_analysis_and_undo(ctrl, csv_files):
    sig = load(ctrl, csv_files[0])[0].signals[0]
    ctrl.workspace_ctrl.push(sig, add(T.MODEL))
    derived = sig.derived_signals[0]

    ctrl.workspace_ctrl.push(sig, make_request(M.REMOVE_ACTION, T.MODEL, index=0))
    assert len(sig.analyses) == 0 and sig.derived_signals == []
    assert _derived_curves(ctrl, sig) == []

    ctrl.workspace_ctrl.undo_stack.undo()
    assert sig.derived_signals == [derived]
    assert _derived_curves(ctrl, sig) == [derived]


def test_derived_curve_follows_analysis(ctrl, csv_files):
    sig = load(ctrl, csv_files[0])[0].signals[0]
    ctrl.workspace_ctrl.push(sig, add(T.MODEL))
    first = sig.derived_signals[0]
    assert _derived_curves(ctrl, sig) == [first]
    # le signal dérivé apparaît sous son analyse dans l'arbre
    analysis_item = ctrl.model.find_signal_item(sig).children[0]
    assert [c.obj for c in analysis_item.children] == [first]

    ctrl.workspace_ctrl.push(sig, make_request(M.MODIFY_ACTION, T.MODEL, {"power": 50.0}, 0))
    assert _derived_curves(ctrl, sig) == sig.derived_signals != [first]

    ctrl.workspace_ctrl.undo_stack.undo()
    assert _derived_curves(ctrl, sig) == [first]


def test_filter_updates_displayed_curve(ctrl, csv_files):
    sig = load(ctrl, csv_files[0])[0].signals[0]
    curve = ctrl.graph_ctrl.curves[sig]
    _ = sig.y  # remplit le cache avant la modification

    ctrl.workspace_ctrl.push(sig, add(T.OFFSET, {"offset": 10.0}))
    np.testing.assert_allclose(sig.y, sig.raw_y + 10.0)
    np.testing.assert_allclose(curve.yData, sig.raw_y + 10.0)

    ctrl.workspace_ctrl.undo_stack.undo()
    np.testing.assert_allclose(curve.yData, sig.raw_y)


def test_push_emits_context_with_node_id(ctrl, csv_files):
    sig = load(ctrl, csv_files[0])[0].signals[0]
    contexts = []
    ctrl.workspace_ctrl.undo_redo_macro_activated.connect(contexts.append)

    ctrl.workspace_ctrl.push(sig, add(T.OFFSET, {"offset": 1.0}))
    ctrl.workspace_ctrl.push(sig, add(T.MODEL))

    assert contexts[0].filter_id == nodes(sig.pipeline)[0].id
    assert contexts[1].analysis_id == nodes(sig.analyses)[0].id


def test_project_reload_keeps_filter_ids(ctrl, csv_files, tmp_path):
    sig = load(ctrl, csv_files[0])[0].signals[0]
    ctrl.workspace_ctrl.push(sig, add(T.OFFSET, {"offset": 1.0}))
    ids = list(sig.pipeline.keys())
    project = tmp_path / "project.json"
    ctrl.workspace.save(project)

    ctrl.import_ctrl.openProject(str(project))

    reloaded = ctrl.workspace.files[0].signals[0]
    assert list(reloaded.pipeline.keys()) == ids
    assert [n.id for n in nodes(reloaded.pipeline)] == ids


def test_parameter_tree_edits_filter_and_analysis(ctrl, csv_files):
    """Chemin du ParameterTree : MainController._on_param_changed(ctx, params)."""
    from ressources.custom_items import SelectionContext, itemType
    sig = load(ctrl, csv_files[0])[0].signals[0]
    ctrl.workspace_ctrl.push(sig, add(T.OFFSET, {"offset": 1.0}))
    ctrl.workspace_ctrl.push(sig, add(T.MODEL))

    filt = nodes(sig.pipeline)[0]
    ctrl._on_param_changed(SelectionContext(role=itemType.FILTER, signal=sig,
                                            filter_id=filt.id), {"offset": 4.0})
    assert nodes(sig.pipeline)[0].get_param("offset") == 4.0

    analysis = nodes(sig.analyses)[0]
    ctrl._on_param_changed(SelectionContext(role=itemType.ANALYSE, signal=sig,
                                            analysis_id=analysis.id), {"power": 20.0})
    assert nodes(sig.analyses)[0].get_param("power") == 20.0
    assert _tree_children(ctrl, sig) == nodes(sig.pipeline) + nodes(sig.analyses)


def test_tree_selection_of_every_item(ctrl, csv_files):
    """Cliquer sur chaque ligne de l'arbre (fichier, signal, filtre, analyse, dérivé)."""
    from PyQt6.QtCore import QItemSelectionModel, QModelIndex
    sig = load(ctrl, csv_files[0])[0].signals[0]
    ctrl.workspace_ctrl.push(sig, add(T.OFFSET, {"offset": 1.0}))
    ctrl.workspace_ctrl.push(sig, add(T.MODEL))

    model, sel = ctrl.model, ctrl.view.treefile.selectionModel()
    def walk(parent):
        for row in range(model.rowCount(parent)):
            index = model.index(row, 0, parent)
            yield index
            yield from walk(index)

    visited = []
    for index in walk(QModelIndex()):
        sel.setCurrentIndex(index, QItemSelectionModel.SelectionFlag.ClearAndSelect)
        visited.append(index.internalPointer().obj.item_type.name)
    assert visited[:2] == ["FILE", "RAW"] and {"FILTER", "ANALYSE", "DERIVED"} <= set(visited)
