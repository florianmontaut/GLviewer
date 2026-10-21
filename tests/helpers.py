# tests/helpers.py
from ressources import custom_items
from ressources.custom_types import ActionModifier


def make_request(modifier, action_type, params=None, index=None):
    return custom_items.ActionRequest(  action_modifier = modifier,
                                        action_type     = action_type,
                                        params          = params or {},
                                        index           = index)


def add(action_type, params=None):
    return make_request(ActionModifier.ADD_ACTION, action_type, params)


def load(ctrl, *paths):
    for path in paths:
        ctrl.import_ctrl.openCsvFiles(path)
    return ctrl.workspace.files


def nodes(ordered):
    """pipeline / analyses sont des OrderedDict id -> node : liste des nodes."""
    return list(ordered.values())
