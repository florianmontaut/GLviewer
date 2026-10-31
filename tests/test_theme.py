# tests/test_theme.py
"""Thème clair / sombre (ressources/theme.py) : graphique, arbres, barre d'outils."""
import pyqtgraph as pg
import pytest
from PyQt6 import QtGui
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


# ---------------- annotations ----------------

from test_annotation_history import _free_text, _curve_annotation, _annotations  # noqa: E402
from test_text_annotations import graph  # noqa: E402,F401


def _shown_colors(item):
    """Couleurs du texte affiché : couleur par défaut et couleurs écrites dans son html."""
    import re
    html = item.textItem.toHtml()
    colors = set(c.lower() for c in re.findall(r"color:\s*(#[0-9a-fA-F]{6})", html))
    return colors | {item.textItem.defaultTextColor().name()}


def test_black_annotation_readable_in_dark_mode(ctrl, graph, monkeypatch):
    """Texte noir (par défaut) affiché clair en sombre ; le projet garde le noir."""
    monkeypatch.setattr(theme.darkdetect, "theme", lambda: "Light")
    item = _free_text(ctrl, graph)
    [annotation] = _annotations(ctrl)
    assert _shown_colors(item) == {"#000000"}

    ctrl.graph_ctrl.updateOptions({"dark_mode": True})
    assert _shown_colors(item) == {theme.DARK["text"].lower()}
    # l'état enregistré est inchangé
    assert item.to_annotation(annotation) == annotation

    ctrl.graph_ctrl.updateOptions({"dark_mode": False})
    assert _shown_colors(item) == {"#000000"}


def test_black_html_readable_in_dark_mode(ctrl, graph, monkeypatch):
    """Noir écrit dans le html par l'éditeur : affiché clair, enregistré noir."""
    monkeypatch.setattr(theme.darkdetect, "theme", lambda: "Light")
    _free_text(ctrl, graph)
    [annotation] = _annotations(ctrl)
    black = annotation.with_changes(
                html='<p><span style=" color:#000000;">Début</span></p>')
    ctrl.graph_ctrl.graph_tree_ctrl.show_annotation(black)
    item = ctrl.graph_ctrl.graph_tree_ctrl.textItems[annotation.id]
    ctrl.graph_ctrl.updateOptions({"dark_mode": True})
    assert _shown_colors(item) == {theme.DARK["text"].lower()}
    assert "color:#000000" in item.to_annotation(black).html


def test_colored_annotation_kept_in_dark_mode(ctrl, graph, monkeypatch):
    """Annotation d'une courbe : couleur de la courbe, quel que soit le thème."""
    monkeypatch.setattr(theme.darkdetect, "theme", lambda: "Light")
    item = _curve_annotation(ctrl, graph)
    [annotation] = _annotations(ctrl)
    curve_color = QtGui.QColor(annotation.color)
    ctrl.graph_ctrl.updateOptions({"dark_mode": True})
    assert item.lineItem.pen().color() == curve_color
    assert item.textItem.defaultTextColor() == curve_color
    assert item.to_annotation(annotation) == annotation


# ---------------- barre de titre ----------------

def test_title_bar_colorref():
    """COLORREF de Windows : 0x00BBGGRR."""
    assert theme._colorref("#123456") == 0x563412


def test_title_bar_ignored_off_windows(ctrl, qapp):
    """Hors fenêtres Windows natives (tests offscreen) : rien n'est demandé à DWM."""
    assert not theme._native_windows()
    theme.style_title_bar(ctrl.view, dark=True)        # sans erreur ni effet
    theme.apply(qapp, dark_mode=False)
    assert theme._title_bar_filter is None
    qapp.setStyleSheet("")
    qapp.setPalette(qapp.style().standardPalette())
