
# controller/main_controller.py

from operator import index

import json
import os
import uuid

import numpy as np
import pandas as pd
import pyqtgraph as pg
from PyQt6 import QtCore,QtGui,QtWidgets,sip

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
from controller.commands.remove_file import RemoveFileCommand
from controller.commands.file_params import ModifyFileParamsCommand
from ressources.custom_commands import od_replace
from controller.channel_tree_controller import ChannelTreeController
from model.channel_tree_model import ChannelTreeModel
from model.channels import (MATCHING_ASK, MATCHING_MODES, MATCHING_SETTINGS, group_channels,
                            same_grouping)
from controller.commands.channel_link import (ChannelLinkCommand, ChannelMatchingCommand,
                                              ChannelGroupsCommand)
from ressources.custom_dialogs import (ChannelMatchingDialog, FormulaDialog,
                                      PowerSourceDialog)
from model.computed import ComputedSignal
from model.formula import FormulaError
from controller.commands.computed_channel import (AddComputedChannelCommand,
                                                  RemoveComputedChannelCommand,
                                                  ModifyComputedChannelCommand)
from controller.benchmark_controller import BenchmarkController
from controller.alignment_controller import AlignmentController

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
        # vue « Par voie » : voies du modèle thermique en attente de la plage (graphique)
        self._pending_model_signals = None
        # puissance de ces modèles (voir _ask_power_source)
        self._pending_power = {}
        self.benchmark_ctrl = None
        # voies calculées : état des données d'entrée lors du dernier tracé
        self._computed_keys = {}
        # contenu du projet au dernier enregistrement (travail non enregistré : voir
        # is_modified) ; défini après la création du workspace
        self._saved_state = None

        # Contrôleurs UI
        self.tree_ctrl      = TreeController(view.treefile)
        # Menu_ctrl en deuxième position afin de récupérer les options utilisateur puis les
        # transmettre aux autres contrôleur
        self.menu_ctrl      = MenuController(view, params, 'MVC_test')
        self.graph_ctrl     = GraphController(view.maingraph,view.graphTree)
        plotItem=[item for item in view.maingraph.items() if isinstance(item,pg.PlotItem)][0]
        self.param_ctrl     = ParameterController(view.selectiontree,plotItem)

        self.cursor_ctrl    = CursorController()
        # vue « Par voie » : même workspace, une voie regroupée sur tous les fichiers
        self.channel_ctrl   = ChannelTreeController(view.treechannels)

        # Contrôleurs fonctionnels
        self.import_ctrl = ImportController(view)
        self.export_ctrl = ExportController(view)

        # Le modèle Qt sera instancié après chargement de fichier
        self.workspace_ctrl = None
        self.model = None
        self.workspace = Workspace()
        self.channel_model = ChannelTreeModel(self.workspace, cursor_value=self._cursor_value)
        self.channel_ctrl.set_model(self.channel_model)
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
        self._connect_channel_signals()
        # recalage d'un fichier dans le temps (« Align in time... »)
        self.alignment_ctrl = AlignmentController(self.graph_ctrl, self.view)
        self.alignment_ctrl.accepted.connect(self._on_alignment_accepted)
        self._mark_saved()

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
        self.view.actionSave.triggered.connect(self.save_project)
        self.view.actionSave_to.triggered.connect(self.save_project_as)
        self.view.close_guard = self.confirm_discard
        self.view.actionAuto_Extract.triggered.connect(lambda: self.export_ctrl.save_to_json(
                                                                    self.workspace))
        self.view.actionQuit.triggered.connect(self.quit)
        self.view.actionBenchmark.triggered.connect(self.show_benchmark)

    # -------------------------------------------------------------------------
    # ENREGISTREMENT DU PROJET
    # -------------------------------------------------------------------------
    def save_project(self) -> bool:
        """Files > Save (Ctrl+S) : dans le projet ouvert, sinon comme « Save as »."""
        if not self.workspace.path:
            return self.save_project_as()
        self.workspace.save(self.workspace.path)
        self._project_saved()
        return True

    def save_project_as(self) -> bool:
        """Files > Save as : nouveau projet .json, ajouté aux fichiers récents."""
        if not self.export_ctrl.save_workspace(self.workspace):
            return False
        self._project_saved()
        return True

    def _project_saved(self):
        self.menu_ctrl.save_recent_file_address(self.workspace.recent_file_params())
        self._mark_saved()
        self.view.statusBar().showMessage(f"Projet enregistré : {self.workspace.path}", 5000)

    def _snapshot(self) -> str:
        """Contenu du projet tel qu'il serait enregistré (comparé à l'enregistrement)."""
        return json.dumps(self.workspace.to_dict(), sort_keys=True, default=str)

    def _mark_saved(self):
        self._saved_state = self._snapshot()
        self._update_title()

    def is_modified(self) -> bool:
        """Travail non enregistré depuis l'ouverture / le dernier enregistrement."""
        return self._snapshot() != self._saved_state

    def _update_title(self, *_):
        if sip.isdeleted(self.view):            # fermeture du logiciel en cours
            return
        path = self.workspace.path
        name = os.path.basename(path) if path else "projet non enregistré"
        star = " *" if self.is_modified() else ""
        self.view.setWindowTitle(f"GLViewer — {name}{star}" if path or star else "GLViewer")

    def confirm_discard(self) -> bool:
        """
        Avant de fermer le logiciel ou d'ouvrir un autre projet : propose d'enregistrer
        le travail non enregistré. False si l'utilisateur annule.
        """
        if not self.is_modified():
            return True
        match self._ask_unsaved_changes():
            case "save":
                return self.save_project()
            case "discard":
                return True
            case _:
                return False

    def _ask_unsaved_changes(self) -> str:
        """« save », « discard » ou « cancel »."""
        name = os.path.basename(self.workspace.path) if self.workspace.path else "Le projet"
        buttons = QtWidgets.QMessageBox.StandardButton
        answer = QtWidgets.QMessageBox.question(
                    self.view, "Modifications non enregistrées",
                    f"{name} a été modifié.\nEnregistrer les modifications ?",
                    buttons.Save | buttons.Discard | buttons.Cancel, buttons.Save)
        return {buttons.Save: "save", buttons.Discard: "discard"}.get(answer, "cancel")

    def show_benchmark(self):
        """Fenêtre « Benchmark » (Options > Benchmark window), créée à la 1re ouverture."""
        if self.benchmark_ctrl is None:
            self.benchmark_ctrl = BenchmarkController(lambda: self.workspace,
                                                      self.channel_model, self.view)
        self.benchmark_ctrl.show()

    def _refresh_benchmark(self, *_):
        """Résultats des modèles modifiés (historique, paramètres d'un fichier...)."""
        if self.benchmark_ctrl is not None:
            self.benchmark_ctrl.refresh()

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
        # un fichier chargé n'est pas une modification à enregistrer (seules les
        # modifications faites ensuite le sont)
        was_saved = not self.is_modified()
        self.workspace.add_file(file_obj)
        self._choose_channel_matching()
        self.channel_model.rebuild()

        if self.model is None:
            # premier fichier : le modèle est construit à partir du workspace
            self._init_workspace_model()
        else:
            self.model.add_file_subtree(file_obj)

        # Seules les courbes du nouveau fichier sont ajoutées au graph
        self._add_file_curves(file_obj)
        self.graph_ctrl.update_vbox()
        if was_saved:
            self._mark_saved()
        else:
            self._update_title()


    def create_workspace(self,workspace:Workspace):
        """
        Remplace le workspace courant (chargement d'un projet .json) et l'attache à
        tous les contrôleurs.
        """
        if not self.confirm_discard():
            return
        self.alignment_ctrl.cancel()
        # nettoyage du graphique de l'ancien workspace
        for sig in list(self.graph_ctrl.curves.keys()):
            self.graph_ctrl.remove_signal_curve(sig)

        self.workspace=workspace
        self.channel_model.workspace = workspace
        self.channel_model.rebuild()

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
        # fichiers récents : le projet plutôt que chacun de ses fichiers
        if self.workspace.path:
            self.menu_ctrl.save_recent_file_address(self.workspace.recent_file_params())
        for file_obj in self.workspace.files:
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
        self._mark_saved()

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
            # signaux dérivés des analyses (projet rechargé) ; un échec est signalé dans
            # l'arbre au lieu d'interrompre le chargement
            sig.refresh_derived()
            for derived in sig.derived_signals:
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
        # fenêtre « Benchmark » : modèles ajoutés, modifiés, annulés...
        self.workspace_ctrl.undo_stack.indexChanged.connect(self._refresh_benchmark)
        # titre de la fenêtre : « * » tant que le travail n'est pas enregistré
        self.workspace_ctrl.undo_stack.indexChanged.connect(self._update_title)

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
        self._sync_derived_curves(sig)
        # un filtre (ou son annulation) change les données d'entrée des analyses
        self._refresh_derived()

    def _sync_derived_curves(self, sig):
        """Courbes du graph = signaux dérivés actuels de sig."""
        for derived in sig.derived_signals:
            self.graph_ctrl.add_signal_curve(derived)

        obsolete = [    curve_sig for curve_sig in self.graph_ctrl.curves
                        if curve_sig.item_type == itemType.DERIVED
                        and curve_sig.parent_signal is sig
                        and curve_sig not in sig.derived_signals]
        for curve_sig in obsolete:
            self.graph_ctrl.remove_signal_curve(curve_sig)

    def _refresh_derived(self):
        """
        Recalcule les analyses dont les données d'entrée ont changé (filtres, undo/redo,
        décalage ou troncature du fichier, signal de référence...), sur tous les signaux,
        puis met à jour l'arbre et les courbes. Les échecs sont signalés.
        """
        if self.model is None:
            return
        self._refresh_computed()
        errors = []
        for file_obj in self.workspace.files:
            for sig in file_obj.signals:
                changed, failed = sig.refresh_derived()
                if not changed:
                    continue
                for analysis in changed:
                    self.model.update_derived(sig, analysis)
                self._sync_derived_curves(sig)
                errors += failed
        if errors:
            self.view.statusBar().showMessage(
                    "Analyse(s) non recalculée(s) : " + " ; ".join(errors), 15000)


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
        # vue « Par voie » : instance de la voie sélectionnée (rien pour un fichier)
        if source != "channels":
            target = ctx.signal if ctx.signal in self.workspace_signals() else None
            self.channel_ctrl.select_signal(target)
        self.channel_model.refresh()
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

    # -------------------------------------------------------------------------
    # VUE « PAR VOIE »
    # -------------------------------------------------------------------------
    def _connect_channel_signals(self):
        self.channel_ctrl.item_selected.connect(
                                    lambda ctx: self.select_from_context(ctx, source="channels"))
        self.channel_model.visibility_changed.connect(self._on_channel_visibility)
        # glisser-déposer : traité après le drop (la vue est reconstruite)
        self.channel_model.link_requested.connect(self.link_channel,
                                                  QtCore.Qt.ConnectionType.QueuedConnection)
        self.channel_ctrl.link_requested.connect(self.link_channel)
        self.channel_ctrl.matching_requested.connect(self.set_channel_matching)
        # groupes de voies, actions sur toutes les voies d'une sélection
        self.channel_ctrl.group_edit_requested.connect(self.edit_channel_groups)
        self.channel_ctrl.apply_requested.connect(self.apply_to_signals)
        self.channel_ctrl.group_selected.connect(
            lambda group: self.param_ctrl.load_params(
                                SelectionContext(role=itemType.CHANNEL_GROUP, signal=group)))
        self.channel_ctrl.has_reference = lambda: self.workspace.reference_signal is not None
        self.channel_model.group_requested.connect(
            lambda keys, gid: self.edit_channel_groups("add", (gid, keys)) if gid is not None
                              else self.edit_channel_groups("remove", keys),
            QtCore.Qt.ConnectionType.QueuedConnection)

    def _choose_channel_matching(self):
        """
        Mode d'appariement des voies d'un nouveau workspace : celui des options, ou, si
        l'option est « demander », question posée au chargement du 2e fichier quand les
        deux modes ne regroupent pas les voies de la même façon.
        """
        workspace = self.workspace
        if workspace.channel_matching is not None:
            return
        mode = MATCHING_SETTINGS.get(self.settings.get("channel_matching", MATCHING_ASK))
        if mode is None:
            if len(workspace.files) < 2 or same_grouping(workspace):
                return
            answer = self._ask_channel_matching()
            if answer is None:                       # annulé : par nom, sans le retenir
                mode = MATCHING_MODES[0]
            else:
                mode, remember = answer
                if remember:
                    self._remember_channel_matching(mode)
        workspace.channel_matching = mode

    def _ask_channel_matching(self):
        """(mode, retenir le choix) ou None si annulé."""
        counts = {mode: sum(len(g.signals) > 1 for g in group_channels(self.workspace, mode))
                  for mode in MATCHING_MODES}
        dialog = ChannelMatchingDialog(counts, parent=self.view)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return None
        return dialog.mode(), dialog.remember.isChecked()

    def _remember_channel_matching(self, mode):
        """Option « Channel matching between files » (Options > Import settings)."""
        label = next(label for label, value in MATCHING_SETTINGS.items() if value == mode)
        options = dict(self.menu_ctrl.params)
        options["channel_matching"] = label
        self.menu_ctrl.get_new_settings(options)

    def link_channel(self, sig, key):
        """Associe à la main sig à la voie logique key (None : appariement automatique)."""
        if sig not in self.workspace_signals():
            return
        mode = self.workspace.matching_mode
        if self.workspace.channel_links.get(mode, {}).get(sig) == key:
            return
        self.workspace_ctrl.undo_stack.push(ChannelLinkCommand(self, sig, key))

    def set_channel_matching(self, mode):
        """Mode d'appariement des voies (par nom / par numéro CH), annulable."""
        if mode != self.workspace.matching_mode or self.workspace.channel_matching is None:
            self.workspace_ctrl.undo_stack.push(ChannelMatchingCommand(self, mode))

    # ---------------- groupes de voies ----------------

    def edit_channel_groups(self, operation: str, arg):
        """
        Groupes de voies de la vue « Par voie » (annulable). Une voie logique n'est que
        dans un seul groupe : l'ajouter à un groupe la retire des autres.
            "new"    : clés des voies          (nom demandé)
            "add"    : (id du groupe, clés)
            "remove" : clés des voies (retirées de leur groupe)
            "rename" : id du groupe            (nom demandé)
            "delete" : id du groupe            (ses voies reviennent hors groupe)
        """
        state = ChannelGroupsCommand.snapshot(self.workspace)
        names = {gid: name for gid, name, _ in state}

        def without(keys):
            return [(gid, name, [k for k in group_keys if k not in keys])
                    for gid, name, group_keys in state]
        match operation:
            case "new":
                name = self._ask_group_name("Nouveau groupe", f"Groupe {len(state) + 1}")
                if not name:
                    return
                state = without(arg) + [(uuid.uuid4().hex, name, list(arg))]
                text = f"New channel group {name}"
            case "add":
                gid, keys = arg
                state = [(g, n, k + list(keys) if g == gid else k)
                         for g, n, k in without(keys)]
                text = f"Add channels to {names.get(gid)}"
            case "remove":
                state = without(arg)
                text = "Remove channels from group"
            case "rename":
                # arg : id du groupe (nom demandé) ou (id, nom) depuis le ParameterTree
                gid, name = arg if isinstance(arg, tuple) else (arg, None)
                if name is None:
                    name = self._ask_group_name("Renommer le groupe", names.get(gid, ""))
                name = (name or "").strip()
                if not name or name == names.get(gid):
                    return
                arg = gid
                state = [(g, name if g == arg else n, k) for g, n, k in state]
                text = f"Rename channel group {name}"
            case "delete":
                state = [entry for entry in state if entry[0] != arg]
                text = f"Delete channel group {names.get(arg)}"
            case _:
                raise ValueError(operation)
        if state != ChannelGroupsCommand.snapshot(self.workspace):
            self.workspace_ctrl.undo_stack.push(ChannelGroupsCommand(self, state, text))

    def _ask_group_name(self, title: str, default: str) -> str | None:
        name, ok = QtWidgets.QInputDialog.getText(self.view, title, "Nom du groupe :",
                                                  text=default)
        return name.strip() if ok and name.strip() else None

    def apply_to_signals(self, signals, action_type):
        """
        Vue « Par voie » : filtre ou analyse sur toutes les voies d'une sélection (voie
        logique, groupe), en une seule entrée de l'historique.
        """
        signals = [sig for sig in signals if sig in self.workspace_signals()]
        if not signals:
            return
        T = custom_types.qSignalType
        if action_type == T.MODEL:
            # puissance puis plage choisies une fois (plage sur le graphique, première
            # voie), puis appliquées à toutes (voir _on_model_range_accepted)
            power = self._ask_power_source(signals)
            if power is None:
                return
            self._pending_power = power
            self._pending_model_signals = signals
            self.graph_ctrl.start_range_selection(signals[0])
            self.view.statusBar().showMessage(self.graph_ctrl.range_picker.HINT)
            return
        if action_type in (T.OFFSET, T.OFFSET_X):
            value = self._ask_group_value(action_type)
            if value is None:
                return
            key = "offset" if action_type == T.OFFSET else "shift_seconds"
            build = lambda sig: ActionRequest(
                                    action_modifier = custom_types.ActionModifier.ADD_ACTION,
                                    action_type     = action_type,
                                    params          = {key: value},
                                    index           = None)
        elif action_type == T.DIFF:
            build = self._group_diff_request
        else:
            build = lambda sig: self._build_action_request(sig, action_type)
        self._push_group(signals, build, action_type)

    def _power_channels(self, signals) -> list:
        """
        Voies logiques pouvant donner la puissance des modèles de signals : présentes
        dans au moins un de leurs fichiers, et ne contenant aucune des voies modélisées.
        """
        files = {sig.file for sig in signals}
        return [channel for channel in self.channel_model.groups()
                if any(s.file in files for s in channel.signals)
                and not any(s in signals for s in channel.signals)]

    def _ask_power_source(self, signals) -> dict | None:
        """
        Source de la puissance des modèles créés sur plusieurs voies : {"channel_key":
        clé de la voie logique}, {"power": valeur} ou {} (valeur par défaut, aucune voie
        possible). None si annulé.
        """
        channels = self._power_channels(signals)
        if not channels:
            return {}
        n_files = len({sig.file for sig in signals})
        choices = []
        for channel in channels:
            n = len({s.file for s in channel.signals} & {sig.file for sig in signals})
            choices.append((f"{channel.name} ({n}/{n_files} essai(s))", channel.key))
        # voie en W proposée par défaut (ex: voie calculée steps(time; ...))
        preferred = next((c.key for c in channels
                          if any(s.unit.strip() == "W" for s in c.signals)), None)
        dialog = PowerSourceDialog(choices, preferred=preferred, parent=self.view)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return None
        return dialog.choice()

    def _model_power_params(self, sig, power: dict) -> dict | str:
        """Paramètres de puissance du modèle de sig (str : voie de puissance absente)."""
        if "power" in power:
            return {"power": power["power"], "power_channel": ""}
        if "channel_key" not in power:
            return {}
        channel = next((c for c in self.channel_model.groups()
                        if c.key == power["channel_key"]), None)
        source = next((s for s in (channel.signals if channel else []) if s.file is sig.file),
                      None)
        if source is None:
            name = channel.name if channel else "?"
            return f"pas de voie de puissance « {name} » dans ce fichier"
        return {"power_channel": source.id}

    def _push_group(self, signals, build, action_type):
        applied, failures = self.workspace_ctrl.push_group(
                                signals, build, f"{action_type.name} on {len(signals)} channels")
        self.view.statusBar().showMessage(f"Action appliquée à {applied} voie(s)", 5000)
        if failures:
            lines = "\n".join(f"• {sig.name} ({sig.file.label or sig.file.name}) : {message}"
                              for sig, message in failures)
            QtWidgets.QMessageBox.warning(self.view, "Action impossible sur certaines voies",
                                          f"{applied} voie(s) traitée(s), "
                                          f"{len(failures)} en échec :\n{lines}")

    def _ask_group_value(self, action_type) -> float | None:
        """Décalage commun à toutes les voies (Y, ou X en secondes)."""
        if action_type == custom_types.qSignalType.OFFSET:
            title, label = "Add an Y offset", "Décalage en Y de toutes les voies :"
        else:
            title, label = "Add an X offset", "Décalage en X de toutes les voies (s) :"
        value, ok = QtWidgets.QInputDialog.getDouble(self.view, title, label, 0.0,
                                                     -1e12, 1e12, 3)
        return value if ok else None

    def _reference_for(self, sig):
        """
        Référence de température de sig : la voie de référence du même essai si elle y
        existe (ex: T AMB de chaque fichier), sinon la référence définie.
        """
        ref = self.workspace.reference_signal
        if ref is None:
            return None
        for channel in self.channel_model.groups():
            if ref in channel.signals:
                same_file = [s for s in channel.signals if s.file is sig.file]
                if same_file:
                    return same_file[0]
        return ref

    def _group_diff_request(self, sig):
        ref = self._reference_for(sig)
        if ref is None or ref is sig:
            return None
        action_type = (custom_types.qSignalType.DIFF if ref.file is sig.file
                       else custom_types.qSignalType.DIFF_EXT)
        return ActionRequest(action_modifier = custom_types.ActionModifier.ADD_ACTION,
                             action_type     = action_type,
                             params          = {'reference': ref},
                             index           = None)

    def workspace_signals(self) -> set:
        return {sig for file_obj in self.workspace.files for sig in file_obj.signals}

    def _cursor_value(self, sig):
        """Valeur au curseur d'une voie (calculée par l'arbre « Par fichier »)."""
        return self.model.cursor_values.get(sig) if self.model is not None else None

    def _on_channel_visibility(self, signals):
        """Cases à cocher de la vue « Par voie » : graphique et arbre « Par fichier »."""
        self._update_title()
        for sig in signals:
            self.graph_ctrl.update_signal(sig)
            if self.model is not None:
                self.model.refresh_object(sig)
                self.model.refresh_check_state(sig.file)

    def _on_visibility_changed(self, item, index=None):
        """
        Un filtre ou une analyse a été ajouté(e) ou modifié(e), il faut mettre à jour la
        courbe correspondante.
        """
        if isinstance(item,TreeItem):
            sig=item.obj
        else:
            sig=item
        self._update_title()
        self.graph_ctrl.update_signal(sig)
        self.channel_model.refresh()
        self._on_cursor_moved(self.model.cursor_x)

    def remove_selected_file(self):
        """
        Retire le fichier de l'élément sélectionné dans le TreeView (fichier, voie, filtre...),
        sans confirmation. Depuis l'interface, voir _delete_selected_item.
        """
        index = self.view.treefile.currentIndex()
        if not index.isValid():
            return
        obj = index.internalPointer().obj
        file_obj = obj if isinstance(obj, FileObject) else getattr(obj, "file", None)
        if file_obj is None:
            sig = index.internalPointer().signal
            file_obj = getattr(sig, "file", None)
        if file_obj in self.workspace.files:
            self.remove_file(file_obj, confirm=False)

    def _dependent_analyses(self, file_obj) -> list:
        """Analyses d'AUTRES fichiers dont la référence est une voie de file_obj."""
        dependents = []
        for other in self.workspace.files:
            if other is file_obj:
                continue
            for sig in other.signals:
                for analysis in sig.analyses.values():
                    # _params : get_params() remplace la référence par son nom
                    ref = analysis._params.get("reference")
                    if isinstance(ref, SignalObject) and ref.file is file_obj:
                        dependents.append((sig, analysis))
        return dependents

    def remove_file(self, file_obj, confirm: bool = True):
        """
        Retire un fichier de l'espace de travail (annulable avec Ctrl+Z). Les données ne
        sont pas supprimées du disque.
        """
        if confirm:
            text = (f"Retirer le fichier « {file_obj.name} » de l'espace de travail ?\n\n"
                    "Le fichier n'est pas supprimé du disque, et l'opération est annulable "
                    "avec Ctrl+Z.")
            dependents = self._dependent_analyses(file_obj)
            if dependents:
                text += (f"\n\n{len(dependents)} analyse(s) d'autres fichiers utilisent une "
                         "de ses voies comme référence : elles seront signalées ⚠.")
            answer = QtWidgets.QMessageBox.question(
                        self.view, "Retirer le fichier", text,
                        QtWidgets.QMessageBox.StandardButton.Yes |
                        QtWidgets.QMessageBox.StandardButton.No,
                        QtWidgets.QMessageBox.StandardButton.No)
            if answer != QtWidgets.QMessageBox.StandardButton.Yes:
                return
        self.workspace_ctrl.undo_stack.push(RemoveFileCommand(self, file_obj))
        self._select_first_available_file()

    def _detach_file(self, file_obj):
        """
        Retire un fichier de l'espace de travail, de l'arbre et du graphique
        (RemoveFileCommand.redo). Le FileObject est conservé pour l'undo.

        Returns:
            la voie de référence (action « référence ») si elle appartenait au fichier
        """
        if self.alignment_ctrl.file is file_obj:
            self.alignment_ctrl.cancel()
        ref = self.workspace.reference_signal
        removed_ref = ref if ref is not None and ref.file is file_obj else None
        if removed_ref is not None:
            self.workspace.set_reference_signal(None)
            self.graph_ctrl.set_reference_signal(None)
            self.tree_ctrl.set_reference_signal(None)

        for sig in file_obj.signals:
            for derived in sig.derived_signals:
                self.graph_ctrl.remove_signal_curve(derived)
            self.graph_ctrl.remove_signal_curve(sig)
        self.workspace.files.remove(file_obj)
        file_obj.removed = True
        self.model.remove_file_subtree(file_obj)
        self.channel_model.rebuild()

        if getattr(self.cursor_ctrl.signal, "file", None) is file_obj:
            self.cursor_ctrl.set_signal(None)
        if self.param_ctrl.shows(file_obj):
            self.param_ctrl.clear()
        # analyses d'autres fichiers dont la référence vient d'être retirée
        self._refresh_derived()
        self.graph_ctrl.update_vbox()
        return removed_ref

    def _attach_file(self, file_obj, index: int, reference=None):
        """Remet un fichier retiré à sa place (RemoveFileCommand.undo)."""
        file_obj.removed = False
        self.workspace.files.insert(index, file_obj)
        self.model.add_file_subtree(file_obj, row=index)
        self.channel_model.rebuild()
        self._add_file_curves(file_obj)
        if reference is not None:
            self.workspace.set_reference_signal(reference)
            self.graph_ctrl.set_reference_signal(reference)
            self.tree_ctrl.set_reference_signal(reference)
        self._refresh_derived()
        self.graph_ctrl.update_vbox()

    def _delete_selected_item(self):
        """
        « Delete selection » / touche Suppr dans l'arbre : retire le fichier (après
        confirmation) ou supprime le filtre / l'analyse sélectionné (annulable).
        """
        index = self.view.treefile.currentIndex()
        if not index.isValid():
            return
        item = index.internalPointer()
        obj = item.obj
        match item.item_type:
            case itemType.FILE:
                self.remove_file(obj)
            case itemType.RAW if obj.is_computed:
                self.workspace_ctrl.undo_stack.push(RemoveComputedChannelCommand(self, obj))
            case itemType.FILTER:
                sig = item.signal
                self.workspace_ctrl.push(sig, ActionRequest(
                                    action_modifier = custom_types.ActionModifier.REMOVE_ACTION,
                                    action_type     = obj.action_type,
                                    params          = {},
                                    index           = sig.get_filter_index_by_id(obj.id)))
            case itemType.ANALYSE:
                sig = item.signal
                self.workspace_ctrl.push(sig, ActionRequest(
                                    action_modifier = custom_types.ActionModifier.REMOVE_ACTION,
                                    action_type     = obj.action_type,
                                    params          = {},
                                    index           = sig.get_analysis_index_by_id(obj.id)))

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
        self.graph_ctrl.range_picker.cancelled.connect(self._on_model_range_cancelled)
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
        signals, self._pending_model_signals = self._pending_model_signals, None
        power, self._pending_power = self._pending_power, {}
        if signals:
            # vue « Par voie » : même plage et même source de puissance pour toutes les
            # voies de la sélection (voie de puissance de chaque essai)
            def build(sig):
                power_params = self._model_power_params(sig, power)
                if isinstance(power_params, str):
                    return power_params
                return ActionRequest(
                            action_modifier = custom_types.ActionModifier.ADD_ACTION,
                            action_type     = custom_types.qSignalType.MODEL,
                            params          = {'model_range': [t_start, t_end],
                                               **power_params},
                            index           = None)
            self._push_group(signals, build, custom_types.qSignalType.MODEL)
            return
        self.workspace_ctrl.push(
                                signal,
                                ActionRequest(
                                    action_modifier = custom_types.ActionModifier.ADD_ACTION,
                                    action_type     = custom_types.qSignalType.MODEL,
                                    params          = {'model_range': [t_start, t_end]},
                                    index           = None
                                    )
                                )


    def _on_model_range_cancelled(self, *_):
        self._pending_model_signals = None
        self._pending_power = {}
        self.view.statusBar().clearMessage()

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
            self.channel_model.refresh()

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
        # paramètres d'un fichier, d'une voie... : enregistrés avec le projet
        QtCore.QTimer.singleShot(0, self._update_title)
        if ctx.role == itemType.CHANNEL_GROUP:
            # groupe de la vue « Par voie » : renommage annulable
            self.edit_channel_groups("rename", (sig.id, new_params.get("name", "")))
            # titre de l'arbre à jour (nom vide refusé : valeur précédente remise) ; différé,
            # l'arbre ne peut pas être reconstruit pendant son propre signal
            QtCore.QTimer.singleShot(0, lambda: self.param_ctrl.load_params(ctx))
            return
        if ctx.filter_id is None and ctx.analysis_id is None and getattr(sig, "is_computed",
                                                                          False):
            self._modify_computed_channel(ctx, new_params)
            return
        if ctx.filter_id is None and ctx.analysis_id is None:
            if isinstance(sig, FileObject):
                # paramètres du fichier : annulables (période, décalage, troncatures...)
                self._modify_file_params(ctx, new_params)
                return
            sig.set_params(new_params)
            self.graph_ctrl.update_signal(sig)
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

        if action_type == custom_types.qSignalType.DEL:
            # fichier, filtre ou analyse : pas forcément de signal visé
            self._delete_selected_item()
            return
        if action_type == custom_types.qSignalType.FORMULA:
            self.add_computed_channel()
            return
        if action_type == custom_types.qSignalType.ALIGN:
            self.start_alignment()
            return
        signal = self._current_signal()
        if signal is None:
            return
        match action_type:
            case  custom_types.qSignalType.REF:
                self._set_selected_signal_as_reference()
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
                self._pending_model_signals = None
                # la plage des données d'entrée est choisie sur le graphique avant la
                # création du modèle (voir _on_model_range_accepted)
                self.graph_ctrl.start_range_selection(signal)
                self.view.statusBar().showMessage(self.graph_ctrl.range_picker.HINT)
            case _:
                action_request=self._build_action_request(signal,action_type)
                self.workspace_ctrl.push(signal,action_request)


    # -------------------------------------------------------------------------
    # VOIES CALCULÉES (formules)
    # -------------------------------------------------------------------------
    def _current_file(self):
        """Fichier visé : fichier sélectionné dans l'arbre, ou fichier de la voie."""
        sel = self.view.treefile.selectionModel().selectedIndexes()
        if not sel:
            return None
        item = sel[0].internalPointer()
        if item.item_type == itemType.FILE:
            return item.obj
        sig = item.action_signal
        return sig.file if isinstance(sig, SignalObject) else None

    def start_alignment(self, file_obj=None):
        """« Align in time... » : recalage à vue du fichier sélectionné (ou de la voie)."""
        file_obj = file_obj or self._current_file()
        if file_obj is not None:
            self.alignment_ctrl.start(file_obj)

    def _on_alignment_accepted(self, file_obj, delta):
        """Recalage validé : décalage du fichier (annulable), analyses recalculées."""
        if file_obj.removed or abs(delta) < 1e-12:
            for sig in list(self.graph_ctrl.curves):
                if getattr(sig, "file", None) is file_obj:
                    self.graph_ctrl.update_signal(sig)
            return
        cmd = ModifyFileParamsCommand(self, file_obj, {"offset": file_obj.offset + delta})
        cmd.setText(f"Align {file_obj.name} ({delta:+g} s)")
        self.workspace_ctrl.undo_stack.push(cmd)
        self.view.statusBar().showMessage(
                f"{file_obj.label or file_obj.name} recalé de {delta:+g} s", 5000)

    def add_computed_channel(self, file_obj=None, defaults=None):
        """
        « Add a computed channel » : nouvelle voie du fichier sélectionné (ou de la voie
        sélectionnée, préremplie dans la formule).
        """
        file_obj = file_obj or self._current_file()
        if file_obj is None:
            return
        sig = self._current_signal()
        if defaults is None:
            defaults = {"formula": f"[{sig.name}]" if sig is not None
                                   and sig.file is file_obj else ""}
        defaults.setdefault("name", self._free_channel_name(file_obj))
        params = self._ask_formula(file_obj, defaults)
        if params is None:
            return
        try:
            new = ComputedSignal(file_obj, **params)
        except ValueError as e:                 # FormulaError compris
            QtWidgets.QMessageBox.warning(self.view, "Voie calculée", str(e))
            return
        self.workspace_ctrl.undo_stack.push(AddComputedChannelCommand(self, new))

    @staticmethod
    def _free_channel_name(file_obj, base="Formula") -> str:
        names = {s.name for s in file_obj.signals}
        n, name = 2, base
        while name in names:
            name, n = f"{base} {n}", n + 1
        return name

    def _attach_signal(self, sig, index):
        """Voie calculée ajoutée (AddComputedChannelCommand) ou remise par un undo."""
        sig.file.signals.insert(index, sig)
        if self.model is not None:
            self.model.insert_signal(sig, index)
        self.graph_ctrl.add_signal_curve(sig)
        self.channel_model.rebuild()
        self._refresh_derived()
        self.select_from_context(SelectionContext(role=itemType.RAW, signal=sig))

    def _detach_signal(self, sig):
        """Voie calculée supprimée (ou ajout annulé)."""
        if self.workspace.reference_signal is sig:
            self.workspace.set_reference_signal(None)
            self.graph_ctrl.set_reference_signal(None)
            self.tree_ctrl.set_reference_signal(None)
        sig.file.signals.remove(sig)
        if self.model is not None:
            self.model.remove_signal(sig)
        for derived in sig.derived_signals:
            self.graph_ctrl.remove_signal_curve(derived)
        self.graph_ctrl.remove_signal_curve(sig)
        if self.param_ctrl.shows(sig.file) and getattr(self.param_ctrl, "_signal", None) is sig:
            self.param_ctrl.clear()
        self.channel_model.rebuild()
        self._refresh_derived()

    def _apply_signal_params(self, sig, params):
        """Paramètres d'une voie calculée (ModifyComputedChannelCommand)."""
        sig.set_params(params)
        self.graph_ctrl.update_signal(sig)
        if self.model is not None:
            self.model.refresh_object(sig)
        self.channel_model.rebuild()
        self._refresh_derived()

    def _modify_computed_channel(self, ctx, new_params):
        sig = ctx.signal
        changed = {k: v for k, v in new_params.items() if sig.get_param(k) != v}
        if not changed:
            return
        formula = {k: v for k, v in changed.items() if k in sig.FORMULA_KEYS}
        if formula:
            ok, message = self.check_formula(sig.file, {**sig.formula_params(), **formula},
                                             current=sig)
            if not ok:
                QtWidgets.QMessageBox.warning(self.view, "Voie calculée", message)
                # valeurs précédentes remises dans l'arbre (différé : son propre signal)
                QtCore.QTimer.singleShot(0, lambda: self.param_ctrl.load_params(ctx))
                return
        self.workspace_ctrl.undo_stack.push(ModifyComputedChannelCommand(self, sig, changed))
        QtCore.QTimer.singleShot(0, lambda: self.param_ctrl.load_params(ctx))

    def _modify_file_params(self, ctx, new_params):
        file_obj = ctx.signal
        changed = {k: v for k, v in new_params.items() if file_obj.get_param(k) != v}
        if not changed:
            return
        try:
            cmd = ModifyFileParamsCommand(self, file_obj, changed)
        except ValueError as e:
            QtWidgets.QMessageBox.warning(self.view, "Paramètres du fichier", str(e))
            # valeurs précédentes remises dans l'arbre (différé : son propre signal)
            QtCore.QTimer.singleShot(0, lambda: self.param_ctrl.load_params(ctx))
            return
        self.workspace_ctrl.undo_stack.push(cmd)

    def _apply_file_params(self, file_obj, params: dict, filter_swaps=()):
        """
        Paramètres d'un fichier (ModifyFileParamsCommand) : filtres passe-bas suivant
        la période, courbes, arbres, analyses et voies calculées.
            filter_swaps : [(signal, filtre actuel, filtre remplaçant)]
        """
        for sig, old, new in filter_swaps:
            sig.pipeline = od_replace(sig.pipeline, old.id, new.id, new)
            sig.pipeline_version += 1
            if self.model is not None:
                self.model.replace_node(sig, old, new, notify=False)
        file_obj.set_params(params)
        for signal in file_obj.signals:
            self.graph_ctrl.update_signal(signal)
        if self.model is not None:
            # libellé de l'arbre (étiquette du fichier, « * » si modifié)
            self.model.refresh_object(file_obj)
        self.channel_model.rebuild()
        # période / décalage / troncature : données d'entrée des analyses modifiées
        self._refresh_derived()
        self._refresh_benchmark()
        if getattr(self.param_ctrl, "_signal", None) is file_obj:
            # valeurs affichées à jour (undo / redo) ; différé : l'arbre peut être
            # en train d'émettre
            ctx = SelectionContext(role=itemType.FILE, signal=file_obj)
            QtCore.QTimer.singleShot(0, lambda: self.param_ctrl.load_params(ctx))

    def _refresh_computed(self):
        """
        Voies calculées dont une donnée d'entrée a changé (filtre sur une voie utilisée,
        décalage d'un fichier...) : courbe et arbre redessinés.
        """
        for file_obj in self.workspace.files:
            for sig in file_obj.signals:
                if not sig.is_computed:
                    continue
                key = sig.input_key()
                if self._computed_keys.get(sig) == key:
                    continue
                self._computed_keys[sig] = key
                self.graph_ctrl.update_signal(sig)
                if self.model is not None:
                    self.model.refresh_object(sig)

    def formula_channels(self, file_obj, exclude=None) -> list[str]:
        """Voies insérables dans une formule du fichier hôte file_obj (le sien d'abord)."""
        host = file_obj
        channels = [f"[{s.name}]" for s in host.signals if s is not exclude] + ["time"]
        for other in self.workspace.files:
            if other is not host:
                prefix = other.label or other.name
                channels += [f"[{prefix}:{s.name}]" for s in other.signals]
        return channels

    @staticmethod
    def check_formula(file_obj, params, current=None) -> tuple[bool, str]:
        """
        Calcul d'essai d'une formule du fichier hôte file_obj : (valide, message affiché
        dans la boîte de saisie). current : voie calculée modifiée (son nom reste libre).
        """
        if not params.get("formula"):
            return False, "Saisissez une formule."
        params = {"name": "Formula", **params}
        try:
            trial = ComputedSignal(file_obj, replaces=current, **params)
            if current is not None:
                # la voie modifiée ne s'utilise pas elle-même (référence circulaire)
                for sig in trial.inputs().values():
                    if sig is current or (sig.is_computed and sig.depends_on(current)):
                        raise FormulaError(f"Circular reference: '{current.name}' would "
                                           f"use itself through {sig.name}")
            x, y, warnings = trial.evaluate()
        except ValueError as e:              # FormulaError compris
            return False, str(e)
        finite = y[np.isfinite(y)]
        unit = params.get("unit", "")
        message = f"{y.size} points"
        if finite.size:
            message += f", de {finite.min():.4g} à {finite.max():.4g} {unit}".rstrip()
        if finite.size < y.size:
            message += f" ({y.size - finite.size} valeurs non définies : nan / inf)"
        if warnings:
            message += "\n" + "\n".join(warnings)
        return True, message

    def _ask_formula(self, file_obj, defaults=None) -> dict | None:
        dialog = FormulaDialog(self.formula_channels(file_obj),
                               lambda params: self.check_formula(file_obj, params),
                               defaults, parent=self.view)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return None
        return dialog.params()

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
        # travail non enregistré : proposé à l'enregistrement (MainWindow.closeEvent)
        self.view.close()
