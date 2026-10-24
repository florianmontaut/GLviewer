# tests/test_chained_actions.py
"""
Enchaîner filtres et analyses sans resélectionner la voie, et projection automatique
du modèle thermique (5 tau) affichée dans le ParameterTree.
"""
import pytest

from ressources.custom_types import qSignalType as T, ActionModifier as M
from ressources.custom_items import SelectionContext, itemType
from helpers import add, load, nodes, make_request


def _select_in_tree(ctrl, obj):
    item = ctrl.model.find_item(ctrl.model.root, obj)
    ctrl.view.treefile.setCurrentIndex(ctrl.model.index_from_item(item))


def _menu(ctrl, action_type):
    ctrl._action_concentrator(M.ADD_ACTION, action_type)


def _selected_obj(ctrl):
    return ctrl.view.treefile.currentIndex().internalPointer().obj


def _menu_enabled(ctrl, label):
    return {a.text(): a.isEnabled() for a in ctrl.tree_ctrl.menu.menu.actions()}[label]


# ---------------- enchaînement des actions ----------------

def test_filters_can_be_chained_without_reselecting(ctrl, csv_files):
    sig = load(ctrl, csv_files[0])[0].signals[0]
    _select_in_tree(ctrl, sig)

    _menu(ctrl, T.OFFSET)
    assert _selected_obj(ctrl) is nodes(sig.pipeline)[0]     # le filtre créé est sélectionné
    _menu(ctrl, T.OFFSET)
    _menu(ctrl, T.FILTER)

    assert [n.action_type for n in nodes(sig.pipeline)] == [T.OFFSET, T.OFFSET, T.FILTER]


def test_model_from_selected_filter_targets_parent_signal(ctrl, csv_files):
    sig = load(ctrl, csv_files[0])[0].signals[0]
    _select_in_tree(ctrl, sig)
    _menu(ctrl, T.OFFSET)

    _menu(ctrl, T.MODEL)                                      # depuis le filtre sélectionné
    picker = ctrl.graph_ctrl.range_picker
    assert picker.is_active and picker.signal is sig
    picker.accept()

    assert len(sig.analyses) == 1


def test_filter_from_selected_analysis_and_derived_signal(ctrl, csv_files):
    sig = load(ctrl, csv_files[0])[0].signals[0]
    ctrl.workspace_ctrl.push(sig, add(T.MODEL))
    analysis = nodes(sig.analyses)[0]

    _select_in_tree(ctrl, analysis)
    _menu(ctrl, T.OFFSET)
    _select_in_tree(ctrl, sig.derived_signals[0])
    _menu(ctrl, T.OFFSET)

    assert len(sig.pipeline) == 2
    assert all(len(d.pipeline) == 0 for d in sig.derived_signals)


def test_reference_from_selected_filter(ctrl, csv_files):
    sig = load(ctrl, csv_files[0])[0].signals[0]
    _select_in_tree(ctrl, sig)
    _menu(ctrl, T.OFFSET)

    _menu(ctrl, T.REF)

    assert ctrl.workspace.reference_signal is sig


def test_file_selection_has_no_target(ctrl, csv_files):
    file_obj = load(ctrl, csv_files[0])[0]
    _select_in_tree(ctrl, file_obj)
    _menu(ctrl, T.OFFSET)
    assert all(len(s.pipeline) == 0 for s in file_obj.signals)


def test_tree_menu_enabled_for_filter_selection(ctrl, csv_files):
    file_obj = load(ctrl, csv_files[0])[0]
    sig = file_obj.signals[0]
    _select_in_tree(ctrl, file_obj)
    assert not _menu_enabled(ctrl, "Get thermal model")

    _select_in_tree(ctrl, sig)
    _menu(ctrl, T.OFFSET)                                     # sélection -> nouveau filtre
    assert _selected_obj(ctrl) is nodes(sig.pipeline)[0]
    assert _menu_enabled(ctrl, "Get thermal model")


# ---------------- projection automatique du modèle thermique ----------------

def _model(ctrl, csv_files, **params):
    sig = load(ctrl, csv_files[0])[0].signals[0]          # échelon tau = 80 s
    ctrl.workspace_ctrl.push(sig, add(T.MODEL, {"model_range": [0.0, 200.0], **params}))
    return sig, nodes(sig.analyses)[0]


def test_auto_projection_reaches_5_tau(ctrl, csv_files):
    sig, analysis = _model(ctrl, csv_files)
    tau = analysis.results.tau

    assert analysis.get_param("projection_auto") is True
    assert analysis.get_param("projection_duration") == pytest.approx(5 * tau - 200, rel=1e-6)
    assert sig.derived_signals[0].x[-1] == pytest.approx(5 * tau, rel=1e-6)


def test_projection_value_shown_in_parameter_tree(ctrl, csv_files):
    sig, analysis = _model(ctrl, csv_files)
    ctrl.param_ctrl.load_params(SelectionContext(role=itemType.ANALYSE, signal=sig,
                                                 analysis_id=analysis.id))
    shown = ctrl.param_ctrl.param.child("Projection duration (s)").value()
    assert shown == pytest.approx(analysis.get_param("projection_duration"))
    assert shown > 0


def test_fit_already_past_5_tau_has_no_projection(ctrl, csv_files):
    sig = load(ctrl, csv_files[0])[0].signals[0]
    ctrl.workspace_ctrl.push(sig, add(T.MODEL, {"model_range": [0.0, 599.0]}))
    analysis = nodes(sig.analyses)[0]
    assert analysis.get_param("projection_duration") == 0.0
    assert sig.derived_signals[0].x[-1] == pytest.approx(599.0)


def test_auto_projection_follows_range_change(ctrl, csv_files):
    sig, analysis = _model(ctrl, csv_files)
    ctrl.workspace_ctrl.push(sig, make_request(M.MODIFY_ACTION, T.MODEL,
                                               {"model_range": [0.0, 300.0]}, 0))
    updated = nodes(sig.analyses)[0]
    assert updated.get_param("projection_auto")
    assert updated.get_param("projection_duration") == pytest.approx(
                                        max(0.0, 5 * updated.results.tau - 300), rel=1e-6)


def test_typed_projection_switches_to_manual(ctrl, csv_files, qapp):
    sig, analysis = _model(ctrl, csv_files)
    ctrl.param_ctrl.load_params(SelectionContext(role=itemType.ANALYSE, signal=sig,
                                                 analysis_id=analysis.id))

    ctrl.param_ctrl.param.child("Projection duration (s)").setValue(1000.0)
    qapp.processEvents()

    updated = nodes(sig.analyses)[0]
    assert updated.get_param("projection_auto") is False
    assert updated.get_param("projection_duration") == 1000.0
    assert sig.derived_signals[0].x[-1] == pytest.approx(1200.0)
    ctrl.workspace_ctrl.undo_stack.undo()
    assert nodes(sig.analyses)[0].get_param("projection_auto") is True


def test_unchecking_auto_keeps_current_projection(ctrl, csv_files, qapp):
    sig, analysis = _model(ctrl, csv_files)
    computed = analysis.get_param("projection_duration")
    ctrl.param_ctrl.load_params(SelectionContext(role=itemType.ANALYSE, signal=sig,
                                                 analysis_id=analysis.id))

    ctrl.param_ctrl.param.child("Auto projection (5 τ)").setValue(False)
    qapp.processEvents()

    updated = nodes(sig.analyses)[0]
    assert updated.get_param("projection_auto") is False
    assert updated.get_param("projection_duration") == pytest.approx(computed)


@pytest.mark.parametrize("saved, expected_auto", [(0.0, True), (1000.0, False)])
def test_legacy_projection(saved, expected_auto):
    from model.analysis.analysis_factory import AnalysisFactory
    node = AnalysisFactory().create_saved({"type": "MODEL",
                                           "params": {"projection_duration": saved}})
    assert node.get_param("projection_auto") is expected_auto


# ---------------- options par défaut (première utilisation) ----------------

def test_fresh_profile_uses_schema_defaults(ctrl):
    params = ctrl.menu_ctrl.params
    assert params["cutoff_frequency"] == 0.003 and params["filter_order"] == 3
    assert params["remove_overrange"] is True


def test_saved_settings_override_defaults(qapp, tmp_path, monkeypatch):
    import json
    from view.main_window import MainWindow
    from controller.menu_controller import MenuController
    from ressources import custom_viewer_settings
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "test_app").mkdir()
    (tmp_path / "test_app" / "settings.json").write_text(
        json.dumps({"files": [], "settings": {"cutoff_frequency": 0.05}}))

    menu = MenuController(MainWindow(), custom_viewer_settings.params, "test_app")

    assert menu.params["cutoff_frequency"] == 0.05      # réglage de l'utilisateur
    assert menu.params["filter_order"] == 3             # défaut du schéma
