from PyQt6 import QtCore,QtWidgets,QtGui

from controller.commands.action_registery import ActionRegistry
from controller.commands.macro import Macro,MacroCommand
from ressources.custom_types import qSignalType, ActionModifier
from ressources.custom_items import ActionRequest,itemType
from ressources.custom_exceptions import MissingParameters,AnalysisError,InvalidModelFit
from ressources.custom_dialogs import AnalysisParamsDialog
from model.base_objects import SignalObject,SelectionContext

class WorkspaceController(QtCore.QObject):

    undo_redo_macro_activated = QtCore.pyqtSignal(SelectionContext)
    macro_created = QtCore.pyqtSignal(Macro)

    def __init__(self, tree_model,graph_ctrl):
        super().__init__()

        self.undo_stack         = QtGui.QUndoStack()
        #graph_ctrl est nécessaire afin de bloquer la MAJ du graphique lors
        #des opérations lourdes du type undo/redo
        self.graph_controller   = graph_ctrl
        self.model              = tree_model
        self.registry           = ActionRegistry()
        self.macros             = {}
        self._macro_buffer      = None

    @property
    def is_recording(self):
        """
        permet de renvoyer un booléen indiquant si Workspace Controller est en
        train d'enregistrer les actions dans une macro
        Returns:
            _type_: _description_
        """
        return  self._macro_buffer is not None

    def start_macro_recording(self):
        self._macro_buffer = []

    #TODO proposer de RAZ le buffer si l'utilisateur essaye de lancer un nouvel
    #TODO enregistrement alors qu'un est déjà en cours
    #! la méthode macro existe déjà dans le package QUndoStack! =>on y trouve également un clearStack
    #! un signal indexChanged
    def stop_macro_recording(self):
        name, ok = QtWidgets.QInputDialog.getText(
                                                    None,
                                                    "Macro",
                                                    "Nom de la macro :"
                                                )
        if not ok:
            return None

        optimized_actions = self._flatten_macro_actions(self._macro_buffer)
        macro = Macro(optimized_actions, name)
        self.macros[name] = macro
        self._macro_buffer = None

        self.macro_created.emit(macro)

    #! ne marche pas
    def _flatten_macro_actions(self, action_requests: list[ActionRequest]) -> list[ActionRequest]:
        """Simplify a recorded macro by collapsing redundant sequential actions."""
        if not action_requests:
            return []

        optimized = []
        latest = {}

        for request in action_requests:
            key = (request.action_type, request.index)
            previous = latest.get(key)

            if request.action_modifier == ActionModifier.ADD_ACTION:
                if previous and previous.action_modifier == ActionModifier.REMOVE_ACTION:
                    # REMOVE then ADD on same target becomes a pure ADD
                    optimized = [r for r in optimized if r is not previous]
                    optimized.append(request)
                    latest[key] = request
                    continue
                optimized.append(request)
                latest[key] = request

            elif request.action_modifier == ActionModifier.MODIFY_ACTION:
                if previous and previous.action_modifier == ActionModifier.ADD_ACTION:
                    # Collapse modify into preceding add if same target
                    previous.params = request.params
                    continue
                if previous and previous.action_modifier == ActionModifier.MODIFY_ACTION:
                    # Keep only the last modify for same target
                    previous.params = request.params
                    continue
                optimized.append(request)
                latest[key] = request

            elif request.action_modifier == ActionModifier.REMOVE_ACTION:
                if previous and previous.action_modifier == ActionModifier.ADD_ACTION:
                    # Add followed by remove cancels out
                    optimized = [r for r in optimized if r is not previous]
                    latest.pop(key, None)
                    continue
                optimized.append(request)
                latest[key] = request

            else:
                optimized.append(request)
                latest[key] = request

        return optimized


    def push(self,sig,action_request:ActionRequest):
        #TODO: utilise l'attribut id des nodes pour les identifier plutôt que par leur position
        #TODO: dans la pile.

        if action_request is None:
            return
        action_request.model = self.model
        try:
            self.graph_controller.freeze_updates(True)
            cmd=self.registry.execute(sig,action_request)
            self.undo_stack.push(cmd)

        except MissingParameters as e:
            self._ask_missing_params( sig,action_request,e.missing_params)

            return
        
        except InvalidModelFit as e:
            print('ligne 130: exception !')
            self._ask_missing_params( sig,action_request,e.missing_params)
            QtWidgets.QMessageBox.warning(
                                            None,
                                            "Analyse impossible",
                                            f"L'analyse a échoué :\n{e}"
                                        )
            return
        
        finally:
            self.graph_controller.freeze_updates(False)

        if self._macro_buffer is not None:
            self._macro_buffer.append(action_request)

        if action_request.action_type in (  qSignalType.MODEL,
                                            qSignalType.FFT,
                                            qSignalType.DIFF_EXT):
            if action_request.index is None:
                index = len(sig.analyses)-1
            else:
                index= action_request.index

            ctx=SelectionContext(
                                    role = itemType.ANALYSE,
                                    signal=sig,
                                    analysis_index=index
                                )
        else:
            if action_request.index is None:
                index = len(sig.pipeline)-1
            else:
                index= action_request.index
            ctx=SelectionContext(
                                    role = itemType.FILTER,
                                    signal=sig,
                                    filter_index=index
                                )
        print(f'workspace PUSH: {ctx}')
        self.undo_redo_macro_activated.emit(ctx)

    def apply_macro(self, macro: Macro|str, signal):

        commands = []
        if isinstance(macro,str):
            macro=self.macros.get(macro,None)
            if macro is None:
                raise AttributeError
        for action_request in macro.action_requests:
            print(f"Applying action: {action_request}")
            #! la méthode modify utilise les listes pipelines et analyses du modèle pour
            #! faire les modifications demandées, il faut donc s'assurer que les action_requests
            #! contiennent des références valides aux objets concernés, ce qui n'est pas le cas
            #! actuellement car les commandes sont empilées/sérialisées et par conséquent les
            #! objest signal ne sont pas modifié dans la boucle for or si on sort de la boucle
            #! for on casse le undo global de la macro, il faudrait donc trouver un moyen de
            #! faire pointer les action_requests vers les bons objets du modèle avant de
            #! les appliquer
            cmd = self.registry.execute(signal, action_request)
            if cmd:
                commands.append(cmd)

        self.undo_stack.push(MacroCommand(commands))

    def _ask_missing_params(    self,
                                signal:         SignalObject,
                                action_request: ActionRequest,
                                missing_params: dict
                            )->dict:

        print('Missing parameter asked!')
        dialog = AnalysisParamsDialog(missing_params,action_request.action_type)
        def resume_creation(new_params):
            merged =    {
                            **action_request.params
                        }
            merged.update(new_params)
            new_request = ActionRequest(
                                        action_modifier=action_request.action_modifier,
                                        action_type=action_request.action_type,
                                        params=merged,
                                        index=action_request.index
                                    )
            self.push(signal, new_request)

        dialog.params_ready.connect(resume_creation)
        dialog.exec()
