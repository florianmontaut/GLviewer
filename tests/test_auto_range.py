# tests/test_auto_range.py
"""
Mise à l'échelle automatique (chargement, « View all ») avec clipToView : l'étendue des
courbes doit être celle des données complètes, pas de la seule partie affichée.
"""
import numpy as np
import pytest

from controller.graph_controller import SignalCurveItem
from helpers import load


@pytest.fixture
def window(ctrl, qapp):
    """Fenêtre ouverte AVANT le chargement (comme dans l'appli) : vue initiale [0, 1]."""
    ctrl.view.resize(1200, 800)
    ctrl.view.show()
    qapp.processEvents()
    return ctrl.graph_ctrl


def _x_view(graph):
    return graph.vb.viewRange()[0]


def test_loaded_file_is_fully_visible(ctrl, window, csv_files, qapp):
    load(ctrl, csv_files[0])                      # x = 0..599 s
    qapp.processEvents()
    x0, x1 = _x_view(window)
    assert x0 <= 0 and x1 >= 599


def test_view_all_after_zoom(ctrl, window, csv_files, qapp):
    load(ctrl, csv_files[0])
    window.vb.setRange(xRange=(100, 110), padding=0)
    qapp.processEvents()

    window.vb.autoRange()                          # « View all »
    x0, x1 = _x_view(window)
    assert x0 <= 0 and x1 >= 599


def test_auto_button_after_zoom(ctrl, window, csv_files, qapp):
    """Bouton « A » de pyqtgraph : auto-échelle activée."""
    load(ctrl, csv_files[0])
    window.vb.setRange(xRange=(100, 110), padding=0)
    qapp.processEvents()

    window.vb.enableAutoRange()
    qapp.processEvents()
    x0, x1 = _x_view(window)
    assert x0 <= 0 and x1 >= 599


def test_second_longer_file_extends_view(ctrl, window, csv_files, tmp_path, qapp):
    from conftest import _write_xy_csv
    load(ctrl, csv_files[0])
    n = 3000
    longer = tmp_path / "long.csv"
    _write_xy_csv(longer, n, np.full(n, 30.0), np.full(n, 31.0))
    load(ctrl, str(longer).replace("\\", "/"))
    qapp.processEvents()
    assert _x_view(window)[1] >= 2999


def test_curves_use_full_bounds_item(ctrl, window, csv_files):
    load(ctrl, csv_files[0])
    assert all(isinstance(c, SignalCurveItem) for c in window.curves.values())


def test_bounds_with_ortho_range_and_fraction(ctrl, window, csv_files, qapp):
    sig = load(ctrl, csv_files[0])[0].signals[0]
    curve = window.curves[sig]
    window.vb.setRange(xRange=(100, 110), padding=0)
    qapp.processEvents()

    assert curve.dataBounds(0) == pytest.approx([0, 599])
    # Y des seuls points de x dans [0, 100] (auto-échelle « visible data only »)
    expected = sig.y[(sig.x >= 0) & (sig.x <= 100)]
    assert curve.dataBounds(1, orthoRange=[0, 100]) == pytest.approx([expected.min(),
                                                                      expected.max()])
    low, high = curve.dataBounds(1, frac=0.5)
    assert sig.y.min() < low < high < sig.y.max()


def test_hidden_curve_ignored_by_view_all(ctrl, window, csv_files, qapp):
    from PyQt6.QtCore import Qt
    file_obj = load(ctrl, csv_files[0])[0]
    ch1, ch2 = file_obj.signals                    # CH1 : 25 -> 45 °C, CH2 : 19-21 °C
    ctrl.model.setData(ctrl.model.signal_index(ch1), Qt.CheckState.Unchecked.value,
                       Qt.ItemDataRole.CheckStateRole)
    window.vb.autoRange()
    y0, y1 = window.vb.viewRange()[1]
    assert y1 < 25
