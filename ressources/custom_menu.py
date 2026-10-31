from PyQt6 import QtCore,QtGui,QtWidgets
from ressources.custom_types import qSignalType
from dataclasses import dataclass


@dataclass
class SelectionState:
    has_selection: bool
    has_reference: bool
    is_recording: bool
    # élément supprimable sélectionné dans l'arbre : fichier, filtre ou analyse
    can_delete: bool = False
    # fichier visé (fichier ou voie sélectionné) : voie calculée
    has_file: bool = False


@dataclass(frozen=True)
class ActionSpec:
    label: str
    enabled_if: callable


class BaseContextMenu(QtCore.QObject):

    ACTION_SPECS = {
                    qSignalType.FILTER : ActionSpec(
                                        label="Filter selection",
                                        enabled_if= lambda s: s.has_selection
                                        ),
                    qSignalType.REF : ActionSpec(
                                        label="Set as temperature ref",
                                        enabled_if= lambda s:   s.has_selection
                                        ),
                    qSignalType.DIFF : ActionSpec(
                                        label="Get temperature rise",
                                        enabled_if= lambda s:   (s.has_selection
                                                                and s.has_reference)
                                        ),
                    qSignalType.OFFSET_X : ActionSpec(
                                        label="Add an X offset",
                                        enabled_if= lambda s: s.has_selection
                                        ),
                    qSignalType.OFFSET : ActionSpec(
                                        label="Add an Y offset",
                                        enabled_if= lambda s: s.has_selection
                                        ),
                    qSignalType.FORMULA : ActionSpec(
                                        label="Add a computed channel",
                                        enabled_if= lambda s: s.has_selection or s.has_file
                                        ),
                    qSignalType.ALIGN : ActionSpec(
                                        label="Align in time...",
                                        enabled_if= lambda s: s.has_selection or s.has_file
                                        ),
                    qSignalType.MODEL : ActionSpec(
                                        label="Get thermal model",
                                        enabled_if= lambda s: s.has_selection
                                        ),
                    qSignalType.ISOLATE : ActionSpec(
                                        label="Isolate selection",
                                        enabled_if= lambda s: s.has_selection
                                        ),
                    qSignalType.START : ActionSpec(
                                        label="Start macro recording",
                                        # disponible pendant un enregistrement : propose
                                        # alors de le recommencer (WorkspaceController)
                                        enabled_if= lambda s: s.has_selection
                                        ),
                    qSignalType.STOP : ActionSpec(
                                        label="Stop macro recording",
                                        enabled_if= lambda s:   (s.has_selection
                                                                and s.is_recording)
                                        ),
                    qSignalType.MACRO : ActionSpec(
                                        label="Apply macro",
                                        enabled_if= lambda s: s.has_selection
                                        ),
                    qSignalType.DEL : ActionSpec(
                                        label="Delete selection",
                                        enabled_if= lambda s: s.can_delete
                                        ),
                    qSignalType.TEXT : ActionSpec(
                                        label="Add text",
                                        enabled_if= lambda s: s.has_selection
                                        )
                    }


    def __init__(self, menu: QtWidgets.QMenu, action_callback):
        super().__init__()
        self.menu = menu
        self._action_callback = action_callback
        self._actions = {}
        self._build_menu()

    def _add_action(self, action_type, payload=None):
        spec=self.ACTION_SPECS[action_type]
        act = QtGui.QAction(spec.label, self.menu)
        act.setData(action_type)
        act.triggered.connect(
                                lambda _, e=action_type, p=payload:
                                            self._action_callback(e, p)
                            )
        self._actions[action_type] = act
        return act

    def _add_submenu(   self, title: str,
                        item:QtGui.QAction|QtWidgets.QMenu=None)-> QtWidgets.QMenu:
        submenu = QtWidgets.QMenu(title, self.menu)
        if item is None:
            self.menu.addMenu(submenu)
        elif isinstance(item,QtGui.QAction):
            self.menu.insertMenu(item,submenu)
        else :
            item.addMenu(submenu)
        return submenu

    def update_enabled_states(self, selection_state:SelectionState):
        for action_type, action in self._actions.items():

            spec = self.ACTION_SPECS[action_type]
            action.setText(spec.label)
            action.setEnabled(spec.enabled_if(selection_state))


    def _build_menu(self):
        raise NotImplementedError


'''
class MacroContextMenuController(QtCore.QObject):

    macro_recording = QtCore.pyqtSignal(qSignalType)
    macro_request = QtCore.pyqtSignal(qSignalType,str)

    def __init__(   self,
                    menu: QtWidgets.QMenu,
                ):
        super().__init__()
        self.menu = menu
        self._build_menu()

    def _build_menu(self):
        self.macro_menu = self.menu.addMenu("Macro")

        self.start_action = QtGui.QAction("Start recording actions", self.menu)
        self.stop_action  = QtGui.QAction("Stop recording", self.menu)

        self.start_action.triggered.connect(lambda x=qSignalType.START:
                                            self.macro_recording.emit(x))
        self.stop_action.triggered.connect(lambda x=qSignalType.STOP:
                                            self.macro_recording.emit(x))
        self.macro_menu.addAction(self.start_action)
        self.macro_menu.addAction(self.stop_action)
        self.macro_menu.addSeparator()
        self.apply_menu = self.macro_menu.addMenu("Apply macro")

    def update_state(self,is_recording):
        self.start_action.setEnabled(not is_recording)
        self.stop_action.setEnabled(is_recording)

    def register_macro(self, macro):
        name=macro.name
        action = QtGui.QAction(name, self.menu)
        action.triggered.connect(lambda x=qSignalType.MACRO,y=name:
                                            self.macro_request.emit(x,y))
        self.apply_menu.addAction(action)'''
