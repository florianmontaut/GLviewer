# tests/test_theme.py
"""Thème clair / sombre (ressources/theme.py) : graphique, arbres, barre d'outils."""
import pyqtgraph as pg
import pytest
from PyQt6.QtCore import Qt

from ressources import theme
from tests.helpers import load


@pytest.fixture
def dark_app(qapp, monkeypatch):
    """Thème sombre appliqué le temps du test (Windows en thème clair)."""
    monkeypatch.setattr(theme.darkdetect, "theme", lambda: "Light")
    theme.apply(qapp, dark_mode=True)
    yield qapp
    qapp.setStyleSheet("")
    qapp.setPalette(qapp.style().standardPalette())


def _background(ctrl):
    return ctrl.graph_ctrl.graph.backgroundBrush().color().name()


def test_graph_background_follows_theme(ctrl, monkeypatch):
    monkeypatch.setattr(theme.darkdetect, "theme", lambda: "Light")
    ctrl.graph_ctrl.updateOptions({"dark_mode": False})
    assert _background(ctrl) == theme.LIGHT["graph_bg"].lower()
    ctrl.graph_ctrl.updateOptions({"dark_mode": True})
    assert _background(ctrl) == theme.DARK["graph_bg"].lower()


def test_custom_graph_background_kept_in_dark_mode(ctrl, monkeypatch):
    """Couleur de fond choisie par l'utilisateur : conservée quel que soit le thème."""
    monkeypatch.setattr(theme.darkdetect, "theme", lambda: "Light")
    ctrl.graph_ctrl.updateOptions({"dark_mode": True, "background_color": "#203040"})
    assert _background(ctrl) == "#203040"


def test_tree_text_follows_theme(ctrl, csv_files):
    """Texte des voies : couleur du thème (pas de noir forcé), référence en rouge."""
    files = load(ctrl, *csv_files)
    sig = files[0].signals[0]
    index = ctrl.model.signal_index(sig)
    assert ctrl.model.data(index, Qt.ItemDataRole.ForegroundRole) is None
    assert not ctrl.model.data(index, Qt.ItemDataRole.DecorationRole).isNull()
    sig.is_reference = True
    brush = ctrl.model.data(index, Qt.ItemDataRole.ForegroundRole)
    assert brush.color() == theme.color("danger")


def test_toolbar_uses_menu_actions(ctrl, csv_files):
    load(ctrl, csv_files[0])        # Undo / Redo : créées au premier fichier ajouté
    view = ctrl.view
    actions = view.toolbar.actions()
    for action in (view.actionLoad_json, view.actionSave, view.actionLoad_csv,
                   view.actionGeneric_csv_file, view.actionBenchmark,
                   view.actionParameters, ctrl.undo_action, ctrl.redo_action):
        assert action in actions
        assert not action.icon().isNull()
    # jamais deux séparateurs de suite
    kinds = [a.isSeparator() for a in actions]
    assert not any(a and b for a, b in zip(kinds, kinds[1:]))


def test_dark_theme_applies_stylesheet(dark_app):
    import main
    sheet = dark_app.styleSheet()
    assert theme.DARK["window"] in sheet
    main.App.toggle_theme(dark_app, {"dark_mode": True})
    assert main.ITEM_VIEW_QSS in dark_app.styleSheet()
    assert pg.getConfigOption("background") == theme.DARK["graph_bg"]
