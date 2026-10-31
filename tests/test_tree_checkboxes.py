# tests/test_tree_checkboxes.py
"""
Cases à cocher de l'arbre « Par fichier » : case d'un fichier (toutes ses courbes),
courbes des analyses, synchronisation avec la vue « Par voie » ; taille des cases du thème.
"""
import pytest
from PyQt6 import QtCore

from ressources.custom_types import qSignalType as T
from helpers import add, load

Qt = QtCore.Qt
CHECK = Qt.ItemDataRole.CheckStateRole


@pytest.fixture
def files(ctrl, csv_files):
    files = list(load(ctrl, *csv_files))
    # une courbe d'analyse sous CH1 de fileA
    ctrl.workspace_ctrl.push(files[0].signals[0], add(T.MODEL, {"model_range": [0.0, 599.0]}))
    return files


def _file_index(ctrl, file_obj):
    return ctrl.model.index_from_item(ctrl.model.find_item(ctrl.model.root, file_obj))


def _state(ctrl, obj):
    if obj.item_type.name == "FILE":
        return ctrl.model.data(_file_index(ctrl, obj), CHECK)
    item = ctrl.model.find_item(ctrl.model.root, obj)
    return ctrl.model.data(ctrl.model.index_from_item(item), CHECK)


def _curves(file_obj):
    return [c for sig in file_obj.signals for c in [sig, *sig.derived_signals]]


def test_file_is_checkable(ctrl, files):
    flags = ctrl.model.flags(_file_index(ctrl, files[0]))
    assert flags & Qt.ItemFlag.ItemIsUserCheckable
    assert _state(ctrl, files[0]) == Qt.CheckState.Checked


def test_uncheck_file_hides_all_its_curves(ctrl, files):
    a, b = files
    ctrl.model.setData(_file_index(ctrl, a), Qt.CheckState.Unchecked.value, CHECK)
    assert len(_curves(a)) == 3                              # CH1, CH2, modèle de CH1
    for curve in _curves(a):
        assert not curve.visible
        assert not ctrl.graph_ctrl.curves[curve].isVisible()
        assert _state(ctrl, curve) == Qt.CheckState.Unchecked
    assert all(c.visible for c in _curves(b))                # autre fichier intact
    assert ctrl.is_modified()

    ctrl.model.setData(_file_index(ctrl, a), Qt.CheckState.Checked.value, CHECK)
    assert all(ctrl.graph_ctrl.curves[c].isVisible() for c in _curves(a))


def test_partial_state(ctrl, files):
    a = files[0]
    sig_item = ctrl.model.find_item(ctrl.model.root, a.signals[1])
    ctrl.model.setData(ctrl.model.index_from_item(sig_item), Qt.CheckState.Unchecked.value,
                       CHECK)
    assert _state(ctrl, a) == Qt.CheckState.PartiallyChecked
    # clic sur la case partielle : tout est affiché
    ctrl.model.setData(_file_index(ctrl, a), Qt.CheckState.Checked.value, CHECK)
    assert a.signals[1].visible and _state(ctrl, a) == Qt.CheckState.Checked


def test_analysis_curve_checkbox(ctrl, files):
    (derived,) = files[0].signals[0].derived_signals
    item = ctrl.model.find_item(ctrl.model.root, derived)
    ctrl.model.setData(ctrl.model.index_from_item(item), Qt.CheckState.Unchecked.value, CHECK)
    assert not derived.visible
    assert not ctrl.graph_ctrl.curves[derived].isVisible()
    assert _state(ctrl, files[0]) == Qt.CheckState.PartiallyChecked


def test_channel_view_updates_file_checkbox(ctrl, files):
    model = ctrl.channel_model
    group = next(row for row, g in enumerate(model.groups()) if g.name == "CH2")
    model.setData(model.index(group, 0), Qt.CheckState.Unchecked.value, CHECK)
    assert _state(ctrl, files[0]) == Qt.CheckState.PartiallyChecked
    assert _state(ctrl, files[1]) == Qt.CheckState.PartiallyChecked


def test_file_checkbox_updates_channel_view(ctrl, files):
    ctrl.model.setData(_file_index(ctrl, files[1]), Qt.CheckState.Unchecked.value, CHECK)
    model = ctrl.channel_model
    group = next(row for row, g in enumerate(model.groups()) if g.name == "CH2")
    assert model.data(model.index(group, 0), CHECK) == Qt.CheckState.PartiallyChecked


def test_theme_checkbox_size(qapp):
    """Cases du thème à la taille du style natif : sinon case et icône dédoublées."""
    import main
    try:
        main.App.toggle_theme(qapp, {"dark_mode": True})
        assert main.ITEM_VIEW_QSS in qapp.styleSheet()
        assert "QAbstractItemView::indicator { width: 14px; height: 14px; }" == \
            main.ITEM_VIEW_QSS
    finally:
        qapp.setStyleSheet("")
        qapp.setPalette(qapp.style().standardPalette())
