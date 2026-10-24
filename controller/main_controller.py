
# controller/main_controller.py

from operator import index

import pandas as pd
import pyqtgraph as pg
from PyQt6 import QtCore,QtGui

from model.base_objects import (DerivedSignalObject, FileObject, SignalObject,
                                Workspace,)
from model.tree_model import PipelineTreeModel

from controller.tree_controller import TreeController
from controller.graph_controller import GraphController
from controller.parameter_controller import ParameterController
from controller.workspace_controller import WorkspaceController
from controller.import_controller import ImportController
from controller.export_controller import ExportController
from controller.menu_controller import MenuController
from controller.cursor_controller import CursorController
from controller.commands.annotations import (AddAnnotationCommand, RemoveAnnotationCommand,
                                             ModifyAnnotationCommand)

from model.tree_item import TreeItem

from ressources import custom_types
from ressources.custom_items import SelectionContext, itemType, ActionRequest

from view.main_window import MainWindow

from dataclasses import dataclass



class MainController(QtCore.QObject):
    """
    Relie l'ensemble des MVC :
        - modèle : FileObject, SignalObject, PipelineTreeModel
        - vue : MainWindow, TreeView, Graph, ParameterTree
        - contrôleurs : TreeController, GraphController, PipelineController, ParameterController

    C’est le cœur de l'application.
    """

    def __init__(self, view : MainWindow, params = dict):
        super().__init__()
        self.view = view
        self.settings={} #? basculer settings dans model ? (PipelineTreeModel) 16/03

        # Contrôleurs UI
        self.tree_ctrl      = TreeController(view.treefile)
        # Menu_ctrl en deuxième position afin de récupérer les options utilisateur puis les
        # transmettre aux autres contrôleur
        self.menu_ctrl      = MenuController(view, params, 'MVC_test')
        self.graph_ctrl     = GraphController(view.maingraph,view.graphTree)
        plotItem=[item for item in view.maingraph.items() if isinstance(item,pg.PlotItem)][0]
        self.param_ctrl     = ParameterController(view.selectiontree,plotItem)

        self.cursor_ctrl    = CursorController()

        # Contrôleurs fonctionnels
        self.import_ctrl = ImportController(view)
        self.export_ctrl = ExportController(view)

        # Le modèle Qt sera instancié après chargement de fichier
        self.workspace_ctrl = None
        self.model = None
        self.workspace = Workspace()
        self.settings = self.menu_ctrl.params
        # accroche du curseur à la courbe sélectionnée : case « snap to selected signal »
        self.on_snap_toggled(self.graph_ctrl.graph_tree_ctrl.mouseCursor.param(
                                                    'snap to selected signal').value())

        # Connexions globales GUI
        self._connect_UI_actions()
        self._connect_tree_signals()
        self._connect_graph_signals()
        self._connect_param_signals()
        self._connect_import_signals()
        self._connect_menu_signals()
        self._connect_cursor_signals()

    # -------------------------------------------------------------------------
    # MENU FILE
    # -------------------------------------------------------------------------
    def _connect_UI_actions(self):
        """
        Connecte les actions de la barre de menu à des slots du MainController.
        """

        self.view.actionLoad_csv.triggered.connect(lambda: self.import_ctrl.load_file_dialog(
                                                    custom_types.fileType.GL))
        self.view.actionLoad_json.triggered.connect(lambda: self.import_ctrl.load_file_dialog(
                                                    custom_types.fileType.JSON))
        self.view.actionImport_txt.triggered.connect(lambda: self.import_ctrl.load_file_dialog(
                                                    custom_types.fileType.TXT))
        self.view.actionGeneric_csv_file.triggered.connect(lambda: self.import_ctrl.
                                                                    load_file_dialog(
                                                                    custom_types.fileType.CSV))
        self.view.actionParameters.triggered.connect( self.menu_ctrl.open_options_window)
        self.view.actionSave_to.triggered.connect(lambda: self.export_ctrl.save_workspace(
                                                                    self.workspace))
        self.view.actionAuto_Extract.triggered.connect(lambda: self.export_ctrl.save_to_json(
                                                                    self.workspace))
        self.view.actionQuit.triggered.connect(self.quit)

    # -------------------------------------------------------------------------
    # LOADING FILE IN THE WORKSPACE
    # -------------------------------------------------------------------------

    def _init_undo_redo(self):
        """
        Initialise les actions Undo/Redo liées à la pile d'actions du WorkspaceController.
        """
        self.undo_action = self.workspace_ctrl.undo_stack.createUndoAction(self.view, "Undo")
        self.redo_action = self.workspace_ctrl.undo_stack.createRedoAction(self.view, "Redo")
        self.undo_action.setShortcut(QtGui.QKeySequence.StandardKey.Undo)
        self.undo_action.setShortcutContext(QtCore.Qt.ShortcutContext.WindowShortcut)

        self.redo_action.setShortcut(QtGui.QKeySequence.StandardKey.Redo)
        self.redo_action.setShortcutContext(QtCore.Qt.ShortcutContext.WindowShortcut)

        self.view.addAction(self.undo_action)
        self.view.addAction(self.redo_action)


    def add_file(self,file_obj:FileObject):
        """
        Ajoute un fichier au workspace, construit le modèle Qt associé et met à jour la vue.
            - file_obj : FileObject à ajouter
        """

        #si le fichier est déjà chargé on sort de méthode
        if file_obj.address in [file.address for file in self.workspace.files]:
            return

        self.menu_ctrl.save_recent_file_address(file_obj.get_file_loader_params())
        self.workspace.add_file(file_obj)

        if self.model is None:
            # premier fichier : le modèle est construit à partir du workspace
            self._init_workspace_model()
        else:
            self.model.add_file_subtree(file_obj)

        # Seules les courbes du nouveau fichier sont ajoutées au graph
        self._add_file_curves(file_obj)
        self.graph_ctrl.update_vbox()


    def create_workspace(self,workspace:Workspace):
        """
        Remplace le workspace courant (chargement d'un projet .json) et l'attache à
        tous les contrôleurs.
        """
        # nettoyage du graphique de l'ancien workspace
        for sig in list(self.graph_ctrl.curves.keys()):
            self.graph_ctrl.remove_signal_curve(sig)

        self.workspace=workspace

        for file_obj in self.workspace.files:
            for sig in file_obj.signals:
                #! ordered dict
                for analysis in sig.analyses.values():
                    #! le treeview ne semble pas être mis à jour et l'index de sélection des courbes
                    #! semble être décalé
                    if analysis.action_type.name == "DIFF_EXT":
                        ref_file =  [   file for file in self.workspace.files if
                                        file.name == analysis.get_param('reference_file')][0]
                        analysis.resolve_reference({s.name: s for s in ref_file.signals})
        # les signaux dérivés sont calculés avant la construction de l'arbre
        # afin qu'ils y apparaissent sous leur analyse
        for file_obj in self.workspace.files:
            self.menu_ctrl.save_recent_file_address(file_obj.get_file_loader_params())
            self._add_file_curves(file_obj)

        self._init_workspace_model()
        # l'historique undo/redo concerne l'ancien workspace
        self.workspace_ctrl.undo_stack.clear()
        self.graph_ctrl.update_vbox()

        # textes du graphique : ceux de l'ancien workspace sont retirés
        annotations_view = self.graph_ctrl.graph_tree_ctrl
        annotations_view.clear_annotations()
        for annotation in self.workspace.annotations.values():
            annotations_view.show_annotation(annotation)

    def _init_workspace_model(self):
        """
        Construit le modèle Qt du workspace courant et l'attache au TreeView.
        Le WorkspaceController (pile undo/redo) n'est créé qu'une seule fois.
        """
        self.model = PipelineTreeModel(self.workspace)
        self.model.node_event.connect(self._on_node_event)
        self.tree_ctrl.set_model(self.model)

        if self.workspace_ctrl is None:
            self.workspace_ctrl = WorkspaceController(self.model,self.graph_ctrl)
            # Create undo/redo actions linked to the stack
            self._init_undo_redo()
            self._connect_workspace_signals()
        else:
            self.workspace_ctrl.model = self.model

    def _add_file_curves(self, file_obj:FileObject):
        """
        Ajoute au graph les courbes d'un fichier et (re)calcule les signaux dérivés
        de ses analyses.
        """
        for sig in file_obj.signals:
            self.graph_ctrl.add_signal_curve(sig)
            #! ordered dict
            for analysis in sig.analyses.values():
                derived = analysis.compute(sig)
                sig.derived_signals.append(derived)
                self.graph_ctrl.add_signal_curve(derived)

    # -------------------------------------------------------------------------
    # TREE SIGNALS
    # -------------------------------------------------------------------------

    def _connect_workspace_signals(self):
        """
        Connecte les signaux émis par le WorkspaceController à des slots du MainController.
        """
        self.workspace_ctrl.undo_redo_macro_activated.connect(self.select_from_context)
        self.workspace_ctrl.macro_created.connect(self._on_macro_created)
        self.workspace_ctrl.recording_changed.connect(self._on_recording_changed)

    def _connect_tree_signals(self):
        """
        Connecte les signaux émis par le TreeController à des slots du MainController.
        """

        self.tree_ctrl.item_selected.connect(
                                                lambda ctx:
                                                self.select_from_context(ctx, source="tree")
                                            )

        self.tree_ctrl.visibility_changed.connect(self._on_visibility_changed)
        self.tree_ctrl.menu_actions_triggered.connect(self._action_concentrator)

    def _get_attached_item(self,signal):

        item_index = self.model.signal_index(signal)
        item = item_index.internalPointer()
        return item

    def _select_signal(self,ctx: SelectionContext):
        if ctx.signal is None:
            obj=ctx.item.obj
        else:
            obj=ctx.signal
        sel_model = self.view.treefile.selectionModel()
        index=self.model.signal_index(obj)
        with QtCore.QSignalBlocker(sel_model):  # ✅ blocage fin et sûr
            sel_model.setCurrentIndex(  index,
                                        QtCore.QItemSelectionModel.
                                        SelectionFlag.ClearAndSelect
                                        )
        # Mise en évidence de la courbe correspondante
        self.graph_ctrl.highlight(obj)
        # Mise à jour du controleur du curseur (on l'attache à la courbe)
        self.cursor_ctrl.set_signal(obj)

        if self.model.cursor_x is None:
            #bug si mous_pos = valeur par défaut (voir graph_controller)
            self.model.updateCursorVal(float(self.graph_ctrl.mouse_pos.x()))
        self.cursor_ctrl.update_x(self.model.cursor_x)

        # notifier le modèle
        #? pourquoi ne pas faire la notification directement dans le tree_controller ?
        self.model.dataChanged.emit( index, index,[QtCore.Qt.ItemDataRole.FontRole])
        self.view.treefile.viewport().update()


    def _clear_selection_flags(self):
        for file in self.workspace.files:
            file.is_selected = False
            for sig in file.signals:
                sig.is_selected = False
                #! ordered dict
                for filt in sig.pipeline.values():
                    filt.is_selected = False
                #! ordered dict
                for analysis in sig.analyses.values():
                    analysis.is_selected = False
                for derived in sig.derived_signals:
                    derived.is_selected = False

    def _on_node_event(self, event):
        ctx : SelectionContext = event.context

        if ctx is None:
            return

        match event.action:
            case custom_types.ActionModifier.ADD_ACTION:
                self._on_node_added(ctx)

            case custom_types.ActionModifier.MODIFY_ACTION:
                self._on_node_changed(ctx)

            case custom_types.ActionModifier.REMOVE_ACTION:
                self._on_node_removed(ctx)

    
    def _on_node_added(self, ctx:SelectionContext):
        if ctx.item is not None:
            self.tree_ctrl.select_tree_from_context(ctx)
        self.param_ctrl.load_params(ctx)
        self._refresh_signal_curves(ctx.signal)


    def _on_node_changed(self, ctx:SelectionContext):
        self.param_ctrl.load_params(ctx)
        self._refresh_signal_curves(ctx.signal)


    def _on_node_removed(self, ctx:SelectionContext):
        self.param_ctrl.load_params(ctx)
        self._refresh_signal_curves(ctx.signal)

    def _refresh_signal_curves(self, sig):
        """
        Met à jour la courbe d'un signal (pipeline de filtres) et synchronise les
        courbes de ses signaux dérivés avec sig.derived_signals (ajout / undo /
        modification d'une analyse).
        """
        self.graph_ctrl.update_signal(sig)

        for derived in sig.derived_signals:
            self.graph_ctrl.add_signal_curve(derived)

        obsolete = [    curve_sig for curve_sig in self.graph_ctrl.curves
                        if curve_sig.item_type == itemType.DERIVED
                        and curve_sig.parent_signal is sig
                        and curve_sig not in sig.derived_signals]
        for curve_sig in obsolete:
            self.graph_ctrl.remove_signal_curve(curve_sig)


    def select_from_context(self, ctx: SelectionContext, source: str = "external"):

        """
        Applique une sélection globale à partir d'un SelectionContext.
        Point d'entrée UNIQUE pour Tree / Graph / externe (undo, macro, etc.)
        """

        if ctx is None or ctx.signal is None:
            return

        # --------------------------------------------------
        # 1. Nettoyage état précédent
        # --------------------------------------------------
        self._clear_selection_flags()
        # --------------------------------------------------
        # 2. Marquer le signal courant
        # --------------------------------------------------
        ctx.signal.is_selected = True
        # --------------------------------------------------
        # 3. Synchronisation TreeView (si nécessaire)
        # --------------------------------------------------
        if source != "tree":
            print(ctx)
            self.tree_ctrl.select_tree_from_context(ctx)
        # --------------------------------------------------
        # 4. Synchronisation Graph (si nécessaire)
        # --------------------------------------------------
        if source != "graph":
            self.graph_ctrl.select_graph_from_context(ctx)
        # courbe mise en évidence (None pour un fichier) : le curseur souris s'y accroche
        self.cursor_ctrl.set_signal(self.graph_ctrl.old_highlight)
        self._refresh_cursor()
        # --------------------------------------------------
        # 5. Chargement ParameterTree
        # --------------------------------------------------
        #print(f'{source}')
        self.param_ctrl.load_params(ctx)


    def on_item_selected(self, ctx: SelectionContext):
        #self._clear_selection_flags()
        #ctx.signal.is_selected = True

        match ctx.role:
            case itemType.RAW:
                self._select_signal(ctx)

                # Chargement des paramètres dans le parameterTree
                self.param_ctrl.load_params(ctx)
            case _:
                self.param_ctrl.load_params(ctx)

    def _on_visibility_changed(self, item, index=None):
        """
        Un filtre ou une analyse a été ajouté(e) ou modifié(e), il faut mettre à jour la
        courbe correspondante.
        """
        if isinstance(item,TreeItem):
            sig=item.obj
        else:
            sig=item
        self.graph_ctrl.update_signal(sig)
        self._on_cursor_moved(self.model.cursor_x)

    def remove_selected_file(self):
        """
        Supprime le FileObject actuellement sélectionné dans le TreeView.
        """

        index = self.view.treefile.currentIndex()
        if not index.isValid():
            return
        item = index.internalPointer()
        obj = item.obj
        # Si l'utilisateur a sélectionné un signal ou un filtre,
        # on remonte au FileObject parent
        if isinstance(obj, SignalObject):
            file_obj = obj.file
        elif isinstance(obj, FileObject):
            file_obj = obj
        else:
            return
        # Retirer les courbes du graph
        for sig in file_obj.signals:
            self.graph_ctrl.remove_signal_curve(sig)
        # Retirer du workspace
        self.workspace.files.remove(file_obj)
        # Retirer du modèle Qt (CRUCIAL)
        self.model.remove_file_subtree(file_obj)
        # Nettoyer curseur / sélection si nécessaire
        if self.cursor_ctrl.signal and self.cursor_ctrl.signal.file is file_obj:
            self.cursor_ctrl.set_signal(None)
        # (optionnel) sélectionner un autre item
        self._select_first_available_file()

    def _select_first_available_file(self):
        """
        Sélectionne automatiquement un autre fichier après suppression.
        """
        if not self.workspace.files:
            return
        index = self.model.index(0, 0, QtCore.QModelIndex())
        self.view.treefile.setCurrentIndex(index)

    # -------------------------------------------------------------------------
    # Import FILE
    # -------------------------------------------------------------------------
    def _connect_import_signals(self):
        """
        Connecte les signaux émis par le ImportController à des slots du MainController.
        """
        self.import_ctrl.file_signal.connect(self.add_file)
        self.import_ctrl.project_signal.connect(self.create_workspace)

    # -------------------------------------------------------------------------
    # Menu Bar signals
    # -------------------------------------------------------------------------
    def _connect_menu_signals(self):
        """
        Connecte les signaux émis par le MenuController à des slots du MainController.
        """
        #? Envoi direct à un autre controller sans vérification du main_controller ?
        self.menu_ctrl.loadSignal.connect(self.import_ctrl.loaderSelect)
        self.menu_ctrl.newOptions.connect(self._on_new_settings)

    def _on_new_settings(self, settings: dict):
        """
        Slot appelé lorsque l'utilisateur modifie les options dans le MenuController.
        """
        self.settings = settings
        self.import_ctrl.updateOptions(settings)
        self.graph_ctrl.updateOptions(settings)

    # -------------------------------------------------------------------------
    # GRAPH SIGNALS
    # -------------------------------------------------------------------------
    def _connect_graph_signals(self):
        """
        Connecte les signaux émis par le GraphController à des slots du MainController.
        """

        self.graph_ctrl.curve_selected.connect(
                                                lambda ctx:
                                                self.select_from_context(ctx, source="graph")
                                                )
        self.graph_ctrl.cursor_moved_X.connect(self._on_cursor_moved)
        self.graph_ctrl.snap_toggled.connect(self.on_snap_toggled)
        self.graph_ctrl.menu_actions_triggered.connect(self._action_concentrator)
        self.graph_ctrl.range_picker.accepted.connect(self._on_model_range_accepted)
        self.graph_ctrl.range_picker.cancelled.connect(
                                                lambda _: self.view.statusBar().clearMessage())
        # textes du graphique : chaque action de l'utilisateur est une commande undo/redo
        annotations_view = self.graph_ctrl.graph_tree_ctrl
        annotations_view.annotation_created.connect(
            lambda a: self._push_annotation_command(
                                    AddAnnotationCommand(self.workspace, annotations_view, a)))
        annotations_view.annotation_changed.connect(
            lambda old, new: self._push_annotation_command(
                        ModifyAnnotationCommand(self.workspace, annotations_view, old, new)))
        annotations_view.annotation_delete_requested.connect(
            lambda a: self._push_annotation_command(
                                RemoveAnnotationCommand(self.workspace, annotations_view, a)))

    def _push_annotation_command(self, cmd):
        """Empile une commande sur un texte (appliquée directement sans fichier chargé)."""
        if self.workspace_ctrl is None:
            cmd.redo()
        else:
            self.workspace_ctrl.undo_stack.push(cmd)

    def _on_model_range_accepted(self, signal, t_start: float, t_end: float):
        """Plage validée sur le graphique : création du modèle thermique."""
        self.view.statusBar().clearMessage()
        self.workspace_ctrl.push(
                                signal,
                                ActionRequest(
                                    action_modifier = custom_types.ActionModifier.ADD_ACTION,
                                    action_type     = custom_types.qSignalType.MODEL,
                                    params          = {'model_range': [t_start, t_end]},
                                    index           = None
                                    )
                                )


    def _connect_cursor_signals(self):

        # Graph + modèle se mettent à jour quand la logique curseur a calculé y
        self.cursor_ctrl.cursor_moved.connect(self._on_cursor_computed)

    def on_snap_toggled(self, enabled):
        self.cursor_ctrl.set_snap(enabled)
        self._refresh_cursor()

    def _refresh_cursor(self):
        """Repositionne le curseur souris (accroche ou courbe sélectionnée modifiée)."""
        if self.model is not None and self.model.cursor_x is not None:
            self.cursor_ctrl.update_x(self.model.cursor_x)

    def _on_cursor_moved(self,x):
        # x est None tant que la souris n'a pas survolé le graphique
        if self.model is None or x is None:
            return
        self.cursor_ctrl.update_x(x)
        # Modèle (pour la colonne "valeur au curseur")
        if self.model:
            # notifie toute la colonne 1 en transmettant la nouvelle valeur de X(valeur)
            self.model.updateCursorVal(x)
            self.view.treefile.viewport().update()

    def _on_cursor_computed(self, coord):
        # Vue
        if isinstance(coord,list):
            x, y_snap = coord
        else:
            x = coord
            y_snap = None
        self.graph_ctrl._update_cursor(x, y_snap)

    # -------------------------------------------------------------------------
    # PARAMETER TREE SIGNALS
    # -------------------------------------------------------------------------
    def _connect_param_signals(self):
        self.param_ctrl.params_changed.connect(self._on_param_changed)

    def _on_param_changed(self, ctx:SelectionContext, new_params):
        """
        Slot appelé lorsque l'utilisateur modifie un paramètre dans le ParameterController.
        """
        """Modification des paramètres d'une analyse."""

        #TODO: utiliser pleinement le SelectionContext, actuellement le role de l'action
        #TODO: n'est pas utilisé
        sig=ctx.signal
        if ctx.filter_id is None and ctx.analysis_id is None:
            sig.set_params(new_params)
            if isinstance(sig,SignalObject):
                self.graph_ctrl.update_signal(sig)
            else:
                #signal est un FileObject, il faut mettre à jour toutes les courbes associées
                for signal in sig.signals:
                    self.graph_ctrl.update_signal(signal)
            return

        # ActionRequest.index est une POSITION (int) : on la retrouve à partir de l'id
        elif ctx.role == itemType.FILTER:
            action_type=sig.get_filter_by_id(ctx.filter_id).action_type
            index=ctx.filter_index
        else:
            action_type=sig.get_analysis_by_id(ctx.analysis_id).action_type
            index=ctx.analysis_index
        self.workspace_ctrl.push(
                                ctx.signal,
                                ActionRequest(
                                    action_modifier = custom_types.ActionModifier.MODIFY_ACTION,
                                    action_type = action_type,
                                    params = new_params,
                                    index = index
                                    )
                                )
        # Mise à jour de la vue, les paramètres des filtres/analyses sont appliqués dans
        # la logique métier du controller de workspace, il suffit juste de rafraîchir la courbe
        '''
        if ctx.filter_index is not None:
            role=itemType.FILTER
        else:
            role=itemType.ANALYSE
        ctx=SelectionContext(
                                role=role,
                                signal=ctx.signal,
                                filter_index=index,
                                analysis_index=ctx.analysis_index,
                                item=None
                            )'''
        # Pas de on_item_selected(ctx) ici : le node modifié a été remplacé par un clone
        # (nouvel id), ctx est donc obsolète. La resélection est faite par le
        # WorkspaceController (undo_redo_macro_activated) et le node_event MODIFY.


    # -------------------------------------------------------------------------
    # HELPERS
    # -------------------------------------------------------------------------

    def _current_signal(self):
        """
        Retourne le signal visé par les actions du menu : le signal sélectionné dans la
        TreeView, ou le signal parent du filtre / de l'analyse / du signal dérivé
        sélectionné (voir TreeItem.action_signal).
        """
        sel = self.view.treefile.selectionModel().selectedIndexes()
        if not sel:
            return None
        sig = sel[0].internalPointer().action_signal
        if isinstance(sig, SignalObject):
            return sig
        return None

    def _rebuild_model(self):
        """
        Reconstruit l'arborescence (utile après reorder).
        """
        if not self.workspace:
            return
        new_model = PipelineTreeModel(self.workspace)
        self.model = new_model
        self.tree_ctrl.set_model(self.model)

        # reconnect pipeline controller
        self.workspace_ctrl.model = new_model


    def _set_selected_signal_as_reference(self):

        sig = self._current_signal()
        if sig is None:
            return

        # 1) Mettre à jour le workspace
        self.workspace.set_reference_signal(sig)
        self.graph_ctrl.set_reference_signal(sig)
        self.tree_ctrl.set_reference_signal(sig)

        # 2) Notifier le modèle (icône + police rouge)
        # Mise à jour ciblée : tous les signaux peuvent être impactés
        for file in self.workspace.files:
            for s in file.signals:
                index = self.model.signal_index(s)
                if index.isValid():
                    self.model.dataChanged.emit(
                                                index,
                                                index,
                                                [
                                                    QtCore.Qt.ItemDataRole.DecorationRole,
                                                    QtCore.Qt.ItemDataRole.FontRole,
                                                    QtCore.Qt.ItemDataRole.ForegroundRole
                                                ]
                                                )

        # 3) (optionnel) Feedback utilisateur
        self.view.statusBar().showMessage(
                                            f"Signal de référence défini : {sig.name}",
                                            3000
                                            )

    def _isolate_signal(self):

        for signal, index in self.model.iter_signal_indexes():
            desired_state = (
                            QtCore.Qt.CheckState.Checked.value
                            if signal.is_selected
                            else QtCore.Qt.CheckState.Unchecked.value
                            )
            self.model.setData(
                                index,
                                desired_state,
                                QtCore.Qt.ItemDataRole.CheckStateRole
                                )

    def _action_concentrator(self,modifier,action_type,macro_name=None):
        """
        Centralise les actions de menu liées aux signaux (isoler, définir comme référence,
        supprimer, appliquer macro, etc.).
        """

        signal = self._current_signal()
        if signal is None:
            return
        match action_type:
            case  custom_types.qSignalType.REF:
                self._set_selected_signal_as_reference()
            case custom_types.qSignalType.DEL:
                pass
                #self.remove_signal(signal)
            case custom_types.qSignalType.ISOLATE:
                self._isolate_signal()
            case custom_types.qSignalType.START:
                # l'état d'enregistrement des menus suit recording_changed
                self.workspace_ctrl.start_macro_recording()
                self.tree_ctrl.checkStates(signal)
                self.graph_ctrl.on_selection_changed(signal)
            case custom_types.qSignalType.STOP:
                self.workspace_ctrl.stop_macro_recording()
                self.tree_ctrl.checkStates(signal)
                self.graph_ctrl.on_selection_changed(signal)
            case custom_types.qSignalType.MACRO:
                self.workspace_ctrl.apply_macro(macro_name,signal)
            case custom_types.qSignalType.MODEL:
                # la plage des données d'entrée est choisie sur le graphique avant la
                # création du modèle (voir _on_model_range_accepted)
                self.graph_ctrl.start_range_selection(signal)
                self.view.statusBar().showMessage(self.graph_ctrl.range_picker.HINT)
            case _:
                action_request=self._build_action_request(signal,action_type)
                self.workspace_ctrl.push(signal,action_request)


    def _build_action_request(self, signal,action_type):
        """
        Méthode générant les actionRequests nécessaire à la création des Nodes
        filter ou analysis qui puissent être annulées via le undo du workspace controller,
        elle centralise également la logique de demande de paramètres
        (ex: cutoff pour les filtres, signal de référence pour les diff, etc.)

        Args:
            signal (SignalObject|DerivedSignalObject): signal concerné par l'action
            action_type (custom_types.qSignalType): type d'action à réaliser (ajout de filtre,
                                                    ajout d'analyse, etc.)

        Returns:
            ActionRequest: structure de données contenant toutes les informations
            nécessaires à la création d'un Node dans le modèle du pipeline, elle est ensuite
            traitée par le workspace controller pour faire les modifications métier et
            mise à jour de la vue
        """

        #ajout d'un filterNode nécessitant des paramètres par défaut
        if action_type in (
                                custom_types.qSignalType.FILTER,
                                custom_types.qSignalType.DIFF,
                            ):
            params = self._ask_filter_params(action_type, signal)
            if action_type == custom_types.qSignalType.DIFF:
                # pas besoin de tester si une référence existe, les règles d'activation des actions
                # sont là pour ça (voir menu_controller)
                if (self.workspace.reference_signal.file != signal.file):
                    # si les signaux comparés proviennent de file différentes
                    # ce n'est pas un simple filtre mais une analyse
                    action_type = custom_types.qSignalType.DIFF_EXT
                    return ActionRequest(
                                        action_modifier =
                                        custom_types.ActionModifier.ADD_ACTION,
                                        action_type = action_type,
                                        params = params,
                                        index = None
                                        )
            #traitement de Filter et diff par le même return
            return ActionRequest(
                                action_modifier =
                                custom_types.ActionModifier.ADD_ACTION,
                                action_type = action_type,
                                params = params,
                                index = None
                                )
        #ajout d'un filterNode ou un analaysisNode
        return ActionRequest(   
                                action_modifier =
                                custom_types.ActionModifier.ADD_ACTION,
                                action_type = action_type,
                                params = {},
                                index = None)

    def _ask_filter_params(self,action_type,sig:SignalObject)->dict:
        """_summary_

        Args:
            action_type (custom_types.qSignalType): type d'action à réaliser (ajout de filtre,
                                                    ajout d'analyse, etc.)
            sig (SignalObject): signal concerné par l'action

        Raises:
            AttributeError: _description_

        Returns:
            dict: dictionnaire contenant les paramètres nécessaires à la création du Node
            (ex: cutoff pour les filtres, signal de référence pour les diff, etc.)
        """

        match action_type:

            case custom_types.qSignalType.FILTER:
                sampling_frequency=1/sig.file.sampling
                return {'cutoff': self.settings["cutoff_frequency"],
                        'fs': sampling_frequency,
                        'order': int(self.settings["filter_order"])
                        }
            case custom_types.qSignalType.DIFF:
                return {'reference':self.workspace.reference_signal}
            case _ :
                raise AttributeError

    def _on_recording_changed(self, is_recording: bool):
        """L'état d'enregistrement de macro est porté par le WorkspaceController."""
        self.tree_ctrl.macro_recording  = is_recording
        self.graph_ctrl.macro_recording = is_recording

    def _on_macro_created(self,macro):

        self.tree_ctrl.menu.add_macro_action(macro)
        self.graph_ctrl.menu.add_macro_action(macro)


    def quit(self):

        if self.workspace_ctrl is None:
            self.view.close()
        else:
            if self.workspace_ctrl.undo_stack.count() >=1:
                self.export_ctrl.save_workspace(self.workspace)
                self.view.close()
            else:
                self.view.close()
