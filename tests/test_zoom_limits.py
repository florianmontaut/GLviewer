# tests/test_zoom_limits.py
"""Graduations adaptatives et limites de zoom du graphique."""
import sys
import time

import numpy as np
import pytest
from PyQt6 import QtCore

from controller.graph_controller import AdaptiveAxisItem
from ressources.custom_types import qSignalType as T
from helpers import add, load


@pytest.fixture
def shown(ctrl, csv_files, qapp):
    """fileA chargé (x ∈ [0, 599] s, CH1 : 25 -> 45 °C, CH2 : sinus 19-21 °C), fenêtre affichée,
    avec les graduations fixes des options par défaut (1200 s / 10 °C)."""
    load(ctrl, csv_files[0])
    ctrl.graph_ctrl.updateOptions(dict(ctrl.graph_ctrl.opts))
    ctrl.view.resize(1200, 800)
    ctrl.view.show()
    qapp.processEvents()
    return ctrl.graph_ctrl


def _view(graph):
    (x0, x1), (y0, y1) = graph.vb.viewRange()
    return x0, x1, y0, y1


def _render(graph, qapp):
    t0 = time.perf_counter()
    graph.graph.grab()
    qapp.processEvents()
    return time.perf_counter() - t0


# ---------------- graduations ----------------

def test_user_tick_spacing_kept_at_normal_zoom(qapp):
    axis = AdaptiveAxisItem('left')
    axis.setTickSpacing(10, 2)
    assert axis.tickSpacing(15, 55, 600) == [(10, 0), (2, 0)]


@pytest.mark.parametrize("span", [1e4, 1e9, 1e15, 1e300])
def test_tick_spacing_adapts_when_dezoomed(qapp, span):
    axis = AdaptiveAxisItem('left')
    axis.setTickSpacing(10, 2)
    levels = axis.tickSpacing(-span, span, 600)
    major = levels[0][0]
    assert 2 * span / major <= AdaptiveAxisItem.MAX_TICKS * 10
    assert axis._tickSpacing == [(10, 0), (2, 0)]        # réglage utilisateur conservé


def test_left_axis_is_adaptive(shown):
    assert isinstance(shown.plot.getAxis('left'), AdaptiveAxisItem)
    assert shown.plot.getAxis('left')._tickSpacing == [(10, 0), (2, 0)]


# ---------------- limites de zoom ----------------

# ±1e300 n'est pas testé : l'écart dépasse la capacité d'un double avant toute limite
# (vue dégénérée [0, 0]) ; inatteignable à la souris, voir test_mouse_wheel_dezoom_is_clamped
@pytest.mark.parametrize("scale", [1e4, 1e6, 1e9, 1e12])
def test_extreme_dezoom_is_clamped_and_renders(ctrl, shown, qapp, qt_errors, monkeypatch, scale):
    errors = []
    monkeypatch.setattr(sys, "excepthook", lambda *e: errors.append(e))
    shown.vb.disableAutoRange()
    shown.vb.setRange(xRange=(-scale, scale), yRange=(-scale, scale), padding=0)

    x0, x1, y0, y1 = _view(shown)
    # au plus 1.5 x l'étendue des données (599 s, ~19 -> 45 °C)
    assert x1 - x0 <= 1.5 * 599 + 1 and y1 - y0 <= 1.5 * 27
    assert x0 >= -0.25 * 599 - 1 and x1 <= 599 * 1.25 + 1
    assert _render(shown, qapp) < 2.0
    assert errors == []


def test_mouse_wheel_dezoom_is_clamped(shown, qapp):
    shown.vb.disableAutoRange()
    for _ in range(60):
        shown.vb.scaleBy((2, 2))
    x0, x1, y0, y1 = _view(shown)
    assert x1 - x0 <= 1.5 * 599 + 1 and y1 - y0 <= 1.5 * 27


def test_extreme_zoom_in_keeps_a_valid_view(shown, qapp):
    shown.vb.disableAutoRange()
    shown.vb.setRange(xRange=(300, 300 + 1e-9), yRange=(30, 30 + 1e-12), padding=0)
    x0, x1, y0, y1 = _view(shown)
    assert x1 - x0 >= 10 * 1.0 - 1e-9          # 10 échantillons (1 s)
    assert y1 - y0 >= 0.01 - 1e-12
    assert _render(shown, qapp) < 2.0


def test_hidden_channels_do_not_widen_limits(ctrl, shown, qapp):
    sig = ctrl.workspace.files[0].signals[0]
    # voie HZ simulée : courbe aux limites du thermocouple, masquée
    from model.base_objects import DerivedSignalObject
    hz = DerivedSignalObject(sig, "HZ", sig.x, np.where(np.arange(len(sig.x)) % 2, -270, 900),
                             pen=sig.pen)
    hz.visible = False
    shown.add_signal_curve(hz)
    shown.curves[hz].setVisible(False)
    shown.update_vbox()

    shown.vb.setRange(yRange=(-1e6, 1e6), padding=0)
    _, _, y0, y1 = _view(shown)
    assert y1 - y0 <= 1.5 * 27


def test_limits_follow_visibility(ctrl, shown, qapp):
    from PyQt6.QtCore import Qt
    ch1, ch2 = ctrl.workspace.files[0].signals
    # seule la sinusoïde (19-21 °C) reste visible : plage Y maximale réduite
    ctrl.model.setData(ctrl.model.signal_index(ch1), Qt.CheckState.Unchecked.value,
                       Qt.ItemDataRole.CheckStateRole)
    shown.vb.setRange(yRange=(-1e6, 1e6), padding=0)
    _, _, y0, y1 = _view(shown)
    assert y1 - y0 <= 1.5 * 2.2

    ctrl.model.setData(ctrl.model.signal_index(ch1), Qt.CheckState.Checked.value,
                       Qt.ItemDataRole.CheckStateRole)
    shown.vb.setRange(yRange=(-1e6, 1e6), padding=0)
    _, _, y0, y1 = _view(shown)
    assert y1 - y0 > 1.5 * 20


def test_limits_include_model_projection(ctrl, shown):
    sig = ctrl.workspace.files[0].signals[0]
    ctrl.workspace_ctrl.push(sig, add(T.MODEL, {"model_range": [0.0, 300.0],
                                                "projection_duration": 1000.0}))
    shown.vb.setRange(xRange=(-1e9, 1e9), padding=0)
    x0, x1, _, _ = _view(shown)
    assert x1 >= 1300            # la projection du modèle (jusqu'à 1300 s) reste atteignable


def test_limits_follow_new_file(ctrl, shown, tmp_path):
    from conftest import _write_xy_csv
    n = 3000
    long_file = tmp_path / "long.csv"
    _write_xy_csv(long_file, n, np.full(n, 30.0), np.full(n, 31.0))
    load(ctrl, str(long_file).replace("\\", "/"))

    shown.vb.setRange(xRange=(-1e9, 1e9), padding=0)
    x0, x1, _, _ = _view(shown)
    assert x1 >= 2999


def test_filter_updates_limits(ctrl, shown):
    sig = ctrl.workspace.files[0].signals[0]
    ctrl.workspace_ctrl.push(sig, add(T.OFFSET, {"offset": 500.0}))
    shown.vb.setRange(yRange=(-1e9, 1e9), padding=0)
    _, _, y0, y1 = _view(shown)
    assert y1 >= 525              # courbe décalée de +500 °C atteignable
