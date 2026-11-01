# tests/test_logic_plot.py
"""
Graphique des voies logiques (0 / 1) au-dessus du graphique principal : voies empilées
et compactées, nom en graduation, valeur au curseur, axe des temps commun, retiré quand
aucune voie logique n'est affichée.
"""
import numpy as np
import pytest
from PyQt6 import QtCore

from helpers import add, load
from ressources.custom_types import qSignalType as T
from test_dalo_import import PERIOD, PRE, write_dalo

Qt = QtCore.Qt


@pytest.fixture
def dalo_file(ctrl, tmp_path):
    ctrl.import_ctrl.openDalo(write_dalo(tmp_path / "event.csv"))
    return ctrl.workspace.files[-1]


def _logic(ctrl):
    return ctrl.graph_ctrl.logic


def _signals(file_obj):
    analog = [s for s in file_obj.signals if not s.is_digital]
    digital = [s for s in file_obj.signals if s.is_digital]
    return analog, digital


def _set_visible(ctrl, sig, visible):
    index = ctrl.model.signal_index(sig)
    ctrl.model.setData(index, (Qt.CheckState.Checked if visible else Qt.CheckState.Unchecked)
                       .value, Qt.ItemDataRole.CheckStateRole)


def _layout_items(ctrl):
    ci = ctrl.graph_ctrl.graph.ci
    return [ci.getItem(row, 0) for row in range(ci.layout.rowCount())
            if ci.getItem(row, 0) is not None]


def test_digital_signals_drawn_in_logic_plot(ctrl, dalo_file):
    logic, main = _logic(ctrl), ctrl.graph_ctrl.plot
    analog, digital = _signals(dalo_file)

    assert logic.shown and _layout_items(ctrl) == [logic.plot, main]
    for sig in digital:
        curve = ctrl.graph_ctrl.curves[sig]
        assert curve in logic.plot.items and curve not in main.items
    for sig in analog:
        assert ctrl.graph_ctrl.curves[sig] in main.items
    # même axe des temps
    assert logic.plot.vb.linkedView(0) is main.vb


def test_rows_ticks_and_step_drawing(ctrl, dalo_file):
    logic = _logic(ctrl)
    pump, fan = _signals(dalo_file)[1]                  # Pump1_On alterne, Fan1_On à 1

    ticks = logic.plot.getAxis('left')._tickLevels[0]
    assert [label for _, label in ticks] == ["Pump1_On", "Fan1_On"]
    assert ticks[0][0] > ticks[1][0]                    # 1re voie en haut
    x, y = ctrl.graph_ctrl.curves[pump].getData()
    base = logic.base(logic.rows[pump])
    np.testing.assert_allclose(np.unique(y), [base, base + logic.HEIGHT])
    # escalier : valeur tenue jusqu'à l'échantillon suivant
    assert len(x) == 2 * len(pump.x)
    assert x[1] == pytest.approx(pump.x[1]) and y[0] == y[1]


def test_hidden_signal_leaves_no_gap(ctrl, dalo_file):
    logic = _logic(ctrl)
    pump, fan = _signals(dalo_file)[1]

    _set_visible(ctrl, pump, False)

    assert logic.rows == {fan: 0}
    assert not ctrl.graph_ctrl.curves[pump].isVisible()
    assert [label for _, label in logic.plot.getAxis('left')._tickLevels[0]] == ["Fan1_On"]


def test_logic_plot_removed_without_visible_digital_signal(ctrl, dalo_file):
    logic, main = _logic(ctrl), ctrl.graph_ctrl.plot
    for sig in _signals(dalo_file)[1]:
        _set_visible(ctrl, sig, False)

    assert not logic.shown and _layout_items(ctrl) == [main]

    _set_visible(ctrl, _signals(dalo_file)[1][1], True)
    assert logic.shown and _layout_items(ctrl) == [logic.plot, main]


def test_left_axes_aligned(ctrl, dalo_file):
    logic, main = _logic(ctrl), ctrl.graph_ctrl.plot
    assert logic.plot.getAxis('left').width() == main.getAxis('left').width()


def test_cursor_values(ctrl, dalo_file):
    logic = _logic(ctrl)
    pump, fan = _signals(dalo_file)[1]
    x = float(pump.x[PRE])                               # échantillon 5 (impair) : Pump1_On = 1

    ctrl._on_cursor_moved(x)

    assert logic.cursor_line.value() == pytest.approx(x) and logic.cursor_line.isVisible()
    assert logic.values[pump].toPlainText() == "1"
    assert logic.values[fan].toPlainText() == "1"
    ctrl._on_cursor_moved(float(pump.x[PRE + 1]))
    assert logic.values[pump].toPlainText() == "0"
    assert logic.values[pump].color.name().upper() == logic.ZERO


def test_click_selects_digital_signal_without_snapping(ctrl, dalo_file):
    pump = _signals(dalo_file)[1][0]
    received = []
    ctrl.graph_ctrl.curve_selected.connect(received.append)

    ctrl.graph_ctrl._on_curve_clicked(ctrl.graph_ctrl.curves[pump], None)

    assert received[0].signal is pump
    assert ctrl.graph_ctrl.old_highlight is pump
    assert ctrl.cursor_ctrl.signal is None               # pas d'accroche sur le 0 / 1


def test_filter_on_digital_signal_redraws_step(ctrl, dalo_file):
    logic = _logic(ctrl)
    fan = _signals(dalo_file)[1][1]
    ctrl.workspace_ctrl.push(fan, add(T.OFFSET, {"offset": -1.0}))   # 1 -> 0
    _, y = ctrl.graph_ctrl.curves[fan].getData()
    np.testing.assert_allclose(y, logic.base(logic.rows[fan]))


def test_removed_file_removes_logic_plot(ctrl, dalo_file):
    ctrl.remove_file(dalo_file, confirm=False)
    logic = _logic(ctrl)
    assert not logic.shown and not logic.curves
    assert _layout_items(ctrl) == [ctrl.graph_ctrl.plot]
    ctrl.workspace_ctrl.undo_stack.undo()
    assert logic.shown and len(logic.curves) == 2


def test_no_logic_plot_for_other_files(ctrl, csv_files):
    load(ctrl, csv_files[0])
    assert not _logic(ctrl).shown
    assert _layout_items(ctrl) == [ctrl.graph_ctrl.plot]
