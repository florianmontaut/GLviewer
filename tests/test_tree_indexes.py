# tests/test_tree_indexes.py
"""Index Qt des signaux : toujours valides, y compris après suppression d'un fichier."""
from PyQt6 import QtCore

from ressources.custom_types import qSignalType as T, ActionModifier as M
from helpers import load


def _select(ctrl, obj):
    ctrl.view.treefile.setCurrentIndex(ctrl.model.index_from_item(ctrl.model.find_item(
                                        ctrl.model.root, obj)))


def _remove_file(ctrl, file_obj):
    _select(ctrl, file_obj)
    ctrl.remove_selected_file()


def test_signal_index_matches_tree_after_file_removal(ctrl, csv_files):
    file_a, file_b = load(ctrl, *csv_files)
    _remove_file(ctrl, file_a)
    assert ctrl.workspace.files == [file_b]

    for sig in file_b.signals:
        index = ctrl.model.signal_index(sig)
        assert index.isValid() and index.internalPointer().obj is sig
        assert index == ctrl.model.index_from_item(ctrl.model.find_signal_item(sig))
    # les signaux du fichier supprimé ne sont plus référencés
    assert not ctrl.model.signal_index(file_a.signals[0]).isValid()


def test_isolate_and_reference_after_file_removal(ctrl, csv_files):
    file_a, file_b = load(ctrl, *csv_files)
    _remove_file(ctrl, file_a)
    keep, other = file_b.signals
    file_a.signals[0].visible = True

    _select(ctrl, keep)
    ctrl._action_concentrator(M.ADD_ACTION, T.ISOLATE)
    assert keep.visible and not other.visible
    # le fichier supprimé n'est plus touché
    assert file_a.signals[0].visible

    ctrl._action_concentrator(M.ADD_ACTION, T.REF)
    assert ctrl.workspace.reference_signal is keep


def test_select_signal_after_file_removal(ctrl, csv_files):
    from ressources.custom_items import SelectionContext, itemType
    file_a, file_b = load(ctrl, *csv_files)
    _remove_file(ctrl, file_a)
    sig = file_b.signals[1]

    ctrl.on_item_selected(SelectionContext(role=itemType.RAW, signal=sig))

    assert ctrl.view.treefile.currentIndex().internalPointer().obj is sig


def test_click_on_derived_curve_selects_its_analysis(ctrl, csv_files):
    from helpers import add, nodes
    sig = load(ctrl, csv_files[0])[0].signals[0]
    ctrl.workspace_ctrl.push(sig, add(T.MODEL))
    derived = sig.derived_signals[0]
    analysis = nodes(sig.analyses)[0]

    ctrl.graph_ctrl._on_curve_clicked(ctrl.graph_ctrl.curves[derived], None)

    assert ctrl.view.treefile.currentIndex().internalPointer().obj is analysis
