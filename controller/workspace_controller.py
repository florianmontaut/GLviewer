import dataclasses

from PyQt6 import QtCore,QtWidgets,QtGui

from controller.commands.action_registery import ActionRegistry
from controller.commands.macro import Macro
from ressources.custom_types import qSignalType, ActionModifier
from ressources.custom_items import ActionRequest,itemType,SelectionContext
from ressources.custom_exceptions import MissingParameters,AnalysisError,InvalidModelFit
from ressources.custom_dialogs import AnalysisParamsDialog
from model.base_objects import SignalObject

class WorkspaceController(QtCore.QObject):

    undo_redo_macro_activated = QtCore.pyqtSignal(SelectionContext)
    macro_created = QtCore.pyqtSignal(Macro)
    # source unique de l'état d'enregistrement (menus du tree et du graph)
    recording_changed = QtCore.pyqtSignal(bool)

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

    def start_macro_recording(self) -> bool:
        """
        Démarre l'enregistrement d'une macro. Si un enregistrement contenant déjà des
        actions est en cours, l'utilisateur choisit de le recommencer (RAZ du buffer)
        ou de le poursuivre.
        Seul le buffer de la macro est remis à zéro : les actions déjà effectuées
        restent dans l'historique et peuvent être annulées (Ctrl+Z).

        Returns:
            bool: True si un nouvel enregistrement (vide) a démarré
        """
        if self._macro_buffer:
            answer = QtWidgets.QMessageBox.question(
                        None,
                        "Macro",
                        f"Un enregistrement est déjà en cours "
                        f"({len(self._macro_buffer)} action(s) enregistrée(s)).\n"
                        "Voulez-vous le recommencer ?\n\n"
                        "Les actions enregistrées seront retirées de la macro, "
                        "mais restent annulables avec Ctrl+Z.",
                        QtWidgets.QMessageBox.StandardButton.Yes |
                        QtWidgets.QMessageBox.StandardButton.No,
                        QtWidgets.QMessageBox.StandardButton.No
                    )
            if answer != QtWidgets.QMessageBox.StandardButton.Yes:
                return False

        self._macro_buffer = []
        self.recording_changed.emit(True)
        return True

    def stop_macro_recording(self):
        name, ok = QtWidgets.QInputDialog.getText(
                                                    None,
                                                    "Macro",
                                                    "Nom de la macro :"
                                                )
        if not ok:
            # l'enregistrement continue
            return None

        optimized_actions = self._flatten_macro_actions(self._macro_buffer)
        macro = Macro(optimized_actions, name)
        self.macros[name] = macro
        self._macro_buffer = None

        self.recording_changed.emit(False)
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


    def push(self,sig,action_request:ActionRequest, errors: list = None) -> bool:
        """
        Crée la commande correspondant à action_request et l'empile dans l'undo_stack.
            errors : si fourni, un échec y est ajouté, (sig, message), au lieu d'être
                     signalé par une boîte de dialogue (voir push_group)

        Returns:
            bool: True si l'action a été appliquée, False si elle a échoué / été annulée
        """
        #TODO: utilise l'attribut id des nodes pour les identifier plutôt que par leur position
        #TODO: dans la pile.

        if action_request is None:
            return False
        action_request.model = self.model
        
        self.graph_controller.freeze_updates(True)
        try:
            # Création de la commande (validation des paramètres) puis, si la commande
            # est de nature à échouer (modélisation / analyse complexe), génération du
            # signal dérivé (prepare) AVANT le push : redo() est appelé par Qt et une
            # exception y serait perdue. En cas d'échec, rien n'est empilé.
            cmd=self.registry.execute(sig,action_request)
            if hasattr(cmd, "prepare"):
                cmd.prepare()

        except MissingParameters as e:
            self._ask_missing_params(sig, action_request, e.missing)
            return False

        except (AnalysisError, RuntimeError, ValueError, IndexError, KeyError) as e:
            #! créer une méthode handleError
            # InvalidModelFit, fit scipy non convergent, paramètres invalides,
            # node introuvable...
            if errors is not None:
                errors.append((sig, str(e)))
                return False
            QtWidgets.QMessageBox.warning(
                                            None,
                                            "Action impossible",
                                            f"L'opération a échoué :\n{e}"
                                        )
            return False

        finally:
            self.graph_controller.freeze_updates(False)

        self.undo_stack.push(cmd)
        index = cmd.index
        
        if self._macro_buffer is not None:
            self._macro_buffer.append(action_request)

        if action_request.action_type in (  qSignalType.MODEL,
                                            qSignalType.FFT,
                                            qSignalType.DIFF_EXT,
                                            qSignalType.FORMULA):
            #TODO: pourquoi ne pas directement passer le node plutôt que se trainer une solution bancale
            analysis_id = sig.get_analysis_id_by_index(index)
            ctx = SelectionContext(
                                    role        = itemType.ANALYSE,
                                    signal      = sig,
                                    analysis_id = analysis_id
                                )
        else:
            filter_id = sig.get_filter_id_by_index(index)
            ctx = SelectionContext(
                                    role        = itemType.FILTER,
                                    signal      = sig,
                                    filter_id   = filter_id
                                )
        print(f'workspace PUSH: {ctx}')
        self.undo_redo_macro_activated.emit(ctx)
        return True

    def push_group(self, signals, build_request, text: str):
        """
        Applique une action à plusieurs voies (vue « Par voie » : voie logique, groupe),
        comme une seule entrée de l'historique : un Ctrl+Z annule tout.
        Une voie en échec (ex: modèle thermique non convergent) n'empêche pas les autres.

        Args:
            signals         : voies visées
            build_request   : callable(sig) -> ActionRequest (None : voie ignorée)
            text            : libellé de l'entrée de l'historique

        Returns:
            (nombre de voies traitées, [(sig, message d'erreur), ...])
        """
        failures = []
        applied = 0
        self.undo_stack.beginMacro(text)
        try:
            for sig in signals:
                request = build_request(sig)
                if request is not None and self.push(sig, request, errors=failures):
                    applied += 1
        finally:
            self.undo_stack.endMacro()
        if not applied:
            # entrée vide : retirée de l'historique (voir apply_macro)
            self.undo_stack.undo()
            self.undo_stack.command(self.undo_stack.index()).setObsolete(True)
            self.undo_stack.redo()
        return applied, failures

    def apply_macro(self, macro: Macro|str, signal) -> bool:
        """
        Applique une macro à un signal, comme une seule entrée de l'historique.

        Chaque action passe par push() entre beginMacro()/endMacro() du QUndoStack :
        elle est construite sur l'état laissé par l'action précédente (index, nodes),
        puis exécutée immédiatement. Un seul Ctrl+Z annule toute la macro.
        Si une action échoue, la macro partiellement appliquée est annulée et
        retirée de l'historique.

        Returns:
            bool: True si toutes les actions ont été appliquées
        """
        if isinstance(macro,str):
            macro=self.macros.get(macro,None)
            if macro is None:
                raise AttributeError
        if not macro.action_requests:
            return True

        self.undo_stack.beginMacro(f"Apply macro {macro.name}")
        success = True
        for action_request in macro.action_requests:
            # copie : la macro enregistrée ne doit pas être modifiée par push()
            request = dataclasses.replace(action_request, params=dict(action_request.params))
            if not self.push(signal, request):
                success = False
                break
        self.undo_stack.endMacro()

        if not success:
            # 1) annulation des actions déjà appliquées de la macro
            self.undo_stack.undo()
            # 2) suppression de la macro de l'historique : avec Qt6, redo() d'une commande
            #    obsolète la supprime SANS l'exécuter (même chose pour undo(), d'où l'ordre)
            self.undo_stack.command(self.undo_stack.index()).setObsolete(True)
            self.undo_stack.redo()
        return success

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
                                        action_modifier = action_request.action_modifier,
                                        action_type     = action_request.action_type,
                                        params          = merged,
                                        index           = action_request.index
                                    )
            self.push(signal, new_request)

        dialog.params_ready.connect(resume_creation)
        dialog.exec()
