# tests/test_highlight.py
"""Mise en évidence (largeur doublée) de la courbe sélectionnée."""
from ressources.custom_types import qSignalType as T, ActionModifier as M
from ressources.custom_items import SelectionContext, itemType
from helpers import add, load, nodes, make_request


def _width(ctrl, sig):
    return ctrl.graph_ctrl.curves[sig].opts['pen'].widthF()


def _base_width(sig):
    return max(sig.pen.widthF(), 1.0)


def _select_signal(ctrl, sig):
    ctrl.select_from_context(SelectionContext(role=sig.item_type, signal=sig), source="tree")
    ctrl.graph_ctrl.select_graph_from_context(SelectionContext(role=sig.item_type, signal=sig))


def _click_curve(ctrl, sig):
    ctrl.graph_ctrl._on_curve_clicked(ctrl.graph_ctrl.curves[sig], None)


def _highlighted(ctrl):
    return [s for s in ctrl.graph_ctrl.curves if _width(ctrl, s) > _base_width(s)]


def test_only_selected_curve_is_highlighted(ctrl, csv_files):
    ch1, ch2 = load(ctrl, csv_files[0])[0].signals
    for sig in (ch1, ch2, ch1, ch2):
        _select_signal(ctrl, sig)
        assert _highlighted(ctrl) == [sig]
        assert _width(ctrl, sig) == 2 * _base_width(sig)


def test_reselecting_does_not_keep_doubling(ctrl, csv_files):
    ch1, ch2 = load(ctrl, csv_files[0])[0].signals
    for _ in range(4):
        _select_signal(ctrl, ch1)
        _select_signal(ctrl, ch1)
        _select_signal(ctrl, ch2)
    assert _width(ctrl, ch1) == _base_width(ch1)
    assert _width(ctrl, ch2) == 2 * _base_width(ch2)


def test_scenario_two_models_after_modification(ctrl, csv_files):
    """
    Scénario signalé : modèle 1 créé puis modifié, 2e modèle sur une autre plage,
    sélection des courbes modèle puis d'un autre objet.
    """
    ch1, ch2 = load(ctrl, csv_files[0])[0].signals
    ctrl.workspace_ctrl.push(ch1, add(T.MODEL))
    _click_curve(ctrl, ch1.derived_signals[0])            # 1er modèle mis en évidence
    ctrl.workspace_ctrl.push(ch1, make_request(M.MODIFY_ACTION, T.MODEL,
                                               {"model_range": [300.0, 599.0]}, 0))
    ctrl.workspace_ctrl.push(ch1, add(T.MODEL, {"model_range": [0.0, 300.0]}))
    second_model = [d for d in ch1.derived_signals
                    if d.metadata['analysis_id'] == nodes(ch1.analyses)[1].id][0]

    for _ in range(3):
        _click_curve(ctrl, second_model)
        assert _highlighted(ctrl) == [second_model]
        _select_signal(ctrl, ch2)
        assert _highlighted(ctrl) == [ch2]

    for derived in ch1.derived_signals:
        assert _width(ctrl, derived) == _base_width(derived)


def test_highlight_survives_curve_update(ctrl, csv_files):
    """Un recalcul (filtre ajouté) ne doit ni perdre ni cumuler la mise en évidence."""
    ch1, ch2 = load(ctrl, csv_files[0])[0].signals
    _select_signal(ctrl, ch1)
    ctrl.workspace_ctrl.push(ch1, add(T.OFFSET, {"offset": 1.0}))
    _select_signal(ctrl, ch1)

    assert _width(ctrl, ch1) == 2 * _base_width(ch1)
    _select_signal(ctrl, ch2)
    assert _width(ctrl, ch1) == _base_width(ch1)


def test_pen_width_changed_by_user_is_kept(ctrl, csv_files):
    ch1, ch2 = load(ctrl, csv_files[0])[0].signals
    _select_signal(ctrl, ch1)
    ch1.pen.setWidth(3)                                   # ex: ParameterTree « Curve pen »
    ctrl.graph_ctrl.update_signal(ch1)

    assert _width(ctrl, ch1) == 6                         # toujours mis en évidence
    _select_signal(ctrl, ch2)
    assert _width(ctrl, ch1) == 3
