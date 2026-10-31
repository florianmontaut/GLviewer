# ressources/theme.py
"""
Thème de l'interface (clair / sombre), en un seul endroit :
    - couleurs de l'application (passées à qdarktheme) et feuille de style complémentaire ;
    - couleurs du graphique pyqtgraph (fond, axes, textes) ;
    - icônes au trait (ressources/icons/*.svg, tracées en « currentColor ») teintées à la
      couleur du thème, ou à celle d'une voie dans les arbres.
L'option « Dark mode » choisit le thème sombre ; sinon, le thème suit celui de Windows.
"""
import pathlib

import darkdetect
import pyqtgraph as pg
import qdarktheme
from PyQt6 import QtCore, QtGui, QtSvg

ICONS = pathlib.Path(__file__).parent / "icons"

LIGHT = {
    "window":       "#F7F8FA",
    "panel":        "#FFFFFF",
    "header":       "#EEF0F3",
    "text":         "#2B2F36",
    "muted":        "#6B7280",
    "border":       "#DDE1E6",
    "accent":       "#0B6BCB",
    "highlight":    "#DCEBFA",
    "danger":       "#C62828",
    "graph_bg":     "#FFFFFF",
    "graph_axis":   "#8A919C",
    "graph_text":   "#4B5361",
}

DARK = {
    "window":       "#1C1F24",
    "panel":        "#22262C",
    "header":       "#2A2E35",
    "text":         "#E3E6EA",
    "muted":        "#9AA3AE",
    "border":       "#353A42",
    "accent":       "#5AA2F0",
    "highlight":    "#24384F",
    "danger":       "#FF6B6B",
    "graph_bg":     "#16181C",
    "graph_axis":   "#6B7380",
    "graph_text":   "#AEB6C0",
}

# fond du graphique par défaut (option « Graph Background color ») : remplacé par celui du
# thème ; une autre couleur choisie par l'utilisateur est conservée
DEFAULT_GRAPH_BACKGROUND = "#ffffff"

# opacité du fond des lignes de voies dans les arbres (couleur de la voie)
ROW_TINT_ALPHA = 45

# Feuille de style ajoutée à celle de qdarktheme : barre d'outils plate, panneaux sans
# cadre, en-têtes discrets.
QSS = """
QToolBar {{
    background: {window};
    border: none;
    border-bottom: 1px solid {border};
    padding: 3px 6px;
    spacing: 2px;
}}
QToolBar QToolButton {{
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 4px;
}}
QToolBar QToolButton:hover {{
    background: {highlight};
}}
QToolBar QToolButton:pressed {{
    border-color: {accent};
}}
QToolBar::separator {{
    background: {border};
    width: 1px;
    margin: 5px 6px;
}}
QFrame#frame, QFrame#frame_4 {{
    border: none;
}}
QTabWidget::pane {{
    border: 1px solid {border};
    border-radius: 4px;
}}
QHeaderView::section {{
    background: {header};
    color: {muted};
    border: none;
    border-right: 1px solid {border};
    padding: 3px 6px;
}}
QStatusBar {{
    background: {window};
    border-top: 1px solid {border};
    color: {muted};
}}
"""

_dark = False
_icon_cache: dict = {}
# actions à icône du thème : réteintées au changement de thème
_themed_actions: list = []


def is_dark(dark_mode: bool = False) -> bool:
    """Thème sombre : option « Dark mode », ou thème sombre de Windows."""
    return bool(dark_mode) or darkdetect.theme() == "Dark"


def colors(dark: bool | None = None) -> dict:
    """Couleurs du thème (thème courant par défaut)."""
    if dark is None:
        dark = _dark
    return DARK if dark else LIGHT


def color(name: str) -> QtGui.QColor:
    return QtGui.QColor(colors()[name])


def _qdarktheme_colors(c: dict) -> dict:
    return {
        "primary":                      c["accent"],
        "background":                   c["window"],
        "foreground":                   c["text"],
        "border":                       c["border"],
        "toolbar.background":           c["window"],
        "statusBar.background":         c["window"],
        "treeSectionHeader.background": c["header"],
        "tableSectionHeader.background": c["header"],
    }


def stylesheet(dark: bool, extra_qss: str = "") -> str:
    c = colors(dark)
    name = "dark" if dark else "light"
    return (qdarktheme.load_stylesheet(name, custom_colors=_qdarktheme_colors(c))
            + QSS.format(**c) + extra_qss)


def palette(dark: bool) -> QtGui.QPalette:
    name = "dark" if dark else "light"
    return qdarktheme.load_palette(name, custom_colors=_qdarktheme_colors(colors(dark)))


def apply(app, dark_mode: bool = False, extra_qss: str = "") -> None:
    """Applique le thème à l'application (feuille de style, palette, pyqtgraph, icônes)."""
    global _dark
    _dark = is_dark(dark_mode)
    c = colors()
    app.setPalette(palette(_dark))
    app.setStyleSheet(stylesheet(_dark, extra_qss))
    # graphiques créés ensuite (ex: fenêtre Benchmark)
    pg.setConfigOption("background", c["graph_bg"])
    pg.setConfigOption("foreground", c["graph_text"])
    _retint_actions()


# ---------------------------------------------------------------- graphique
def graph_background(option_color, dark: bool | None = None):
    """Fond du graphique : celui du thème si l'option est restée à sa valeur par défaut."""
    if pg.mkColor(option_color).name().lower() == DEFAULT_GRAPH_BACKGROUND:
        return colors(dark)["graph_bg"]
    return option_color


def style_plot(plot_item: pg.PlotItem, dark: bool | None = None) -> None:
    """Axes et textes d'un PlotItem aux couleurs du thème (la grille suit les axes)."""
    c = colors(dark)
    for name in ("left", "bottom", "right", "top"):
        axis = plot_item.getAxis(name)
        axis.setPen(pg.mkPen(c["graph_axis"]))
        axis.setTextPen(pg.mkPen(c["graph_text"]))


# ---------------------------------------------------------------- icônes
def icon(name: str, tint=None) -> QtGui.QIcon:
    """
    Icône ressources/icons/<name>.svg tracée à la couleur tint (QColor ou "#rrggbb"),
    par défaut celle des icônes du thème courant.
    """
    tint = QtGui.QColor(tint if tint is not None else colors()["muted"])
    key = (name, tint.name(QtGui.QColor.NameFormat.HexArgb))
    cached = _icon_cache.get(key)
    if cached is not None:
        return cached
    svg = (ICONS / f"{name}.svg").read_text(encoding="utf-8")
    svg = svg.replace("currentColor", tint.name())
    if tint.alpha() < 255:
        svg = svg.replace("<svg ", f'<svg opacity="{tint.alphaF():.3f}" ', 1)
    renderer = QtSvg.QSvgRenderer(QtCore.QByteArray(svg.encode("utf-8")))
    result = QtGui.QIcon()
    for size in (16, 24, 32, 48):
        pixmap = QtGui.QPixmap(size, size)
        pixmap.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        result.addPixmap(pixmap)
    _icon_cache[key] = result
    return result


def set_action_icon(action: QtGui.QAction, name: str) -> None:
    """Icône du thème sur une action, réteintée au changement de thème."""
    action.setIcon(icon(name))
    _themed_actions.append((action, name))


def _retint_actions() -> None:
    alive = []
    for action, name in _themed_actions:
        try:
            action.setIcon(icon(name))
        except RuntimeError:    # action détruite (fenêtre fermée)
            continue
        alive.append((action, name))
    _themed_actions[:] = alive


def row_tint(pen_color) -> QtGui.QBrush:
    """Fond discret d'une ligne de voie dans les arbres : couleur de la voie, très atténuée."""
    tint = QtGui.QColor(pen_color)
    tint.setAlpha(ROW_TINT_ALPHA)
    return QtGui.QBrush(tint)
