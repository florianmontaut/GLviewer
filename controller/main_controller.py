
# controller/main_controller.py

from operator import index

import pandas as pd
from PyQt6 import QtCore,QtGui

from model.base_objects import DerivedSignalObject, FileObject, SignalObject,Workspace
from model.tree_model import PipelineTreeModel

from controller.tree_controller import TreeController
from controller.graph_controller import GraphController
from controller.parameter_controller import ParameterController
from controller.workspace_controller import WorkspaceController
from controller.import_controller import ImportController
from controller.export_controller import ExportController
from controller.menu_controller import MenuController
from controller.cursor_controller import CursorController


from model.analysis import fft,thermal
from model.tree_item import TreeItem

from ressources import custom_types,custom_items

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
        self.param_ctrl     = ParameterController(view.selectiontree)

        self.cursor_ctrl    = CursorController()

        # Contrôleurs fonctionnels
        self.import_ctrl = ImportController(view)
        self.export_ctrl = ExportController(view)

        # Le modèle Qt sera instancié après chargement de fichier
        self.workspace_ctrl = None
        self.model = None
        self.workspace = Workspace()
        self.settings = self.menu_ctrl.params
        self.on_snap_toggled(True)

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
        #self.edit_menu = self.view.menuBar().addMenu("Edit")
        #self.edit_menu.addAction(self.undo_action)
        #self.edit_menu.addAction(self.redo_action)

    def add_file(self,file_obj:FileObject):
        """
        Ajoute un fichier au workspace, construit le modèle Qt associé et met à jour la vue.
            - file_obj : FileObject à ajouter
        """

        if self.workspace is None:
            self.create_workspace()
        else:
            #si le fichier est déjà chargé on sort de méthode
            if file_obj.address in [file.address for file in self.workspace.files]:
                return

        self.menu_ctrl.save_recent_file_address([file_obj.file_type,file_obj.address])
        self.workspace.add_file(file_obj)

        # Construire QAbstractItemModel
        if self.model is None:
            self.model = PipelineTreeModel(self.workspace)
            self.model.new_filter.connect(self._on_filter_added)
            self.model.new_analysis.connect(self._on_analysis_added)
            self.model.changed_filter.connect(self._on_filter_changed)
        else:
            self.model.add_file_subtree(file_obj)

        # Attacher modèle → TreeView
        self.tree_ctrl.set_model(self.model)

        # PipelineController avec UndoStack
        self.workspace_ctrl = WorkspaceController(self.model)
        # Create undo/redo actions linked to the stack
        self._init_undo_redo()
        self._connect_workspace_signals()
        # Ajouter toutes les courbes au graph
        for file_obj in self.workspace.files:
            for sig in file_obj.signals:
                self.graph_ctrl.add_signal_curve(sig)
                for analysis in sig.analyses:
                    derived = analysis.compute(sig)
                    sig.derived_signals.append(derived)
                    self.graph_ctrl.add_signal_curve(derived)
        self.graph_ctrl.update_vbox()


    def create_workspace(self,workspace:Workspace):
        """
        Créer un nouveau workspace et l'attacher à tous les contrôleurs.
        """

        self.workspace=workspace
        self.model = PipelineTreeModel(self.workspace)
        self.model.new_filter.connect(self._on_filter_added)
        self.model.changed_filter.connect(self._on_filter_changed)
        self.tree_ctrl.set_model(self.model)
        self.workspace_ctrl = WorkspaceController(self.model)

        # Create undo/redo actions linked to the stack
        self._init_undo_redo()
        self._connect_workspace_signals()

        for file_obj in self.workspace.files:
            self.menu_ctrl.save_recent_file_address([file_obj.file_type,file_obj.address])
            for sig in file_obj.signals:
                self.graph_ctrl.add_signal_curve(sig)
                for analysis in sig.analyses:
                    derived = analysis.compute(sig)
                    sig.derived_signals.append(derived)
                    self.graph_ctrl.add_signal_curve(derived)
        self.graph_ctrl.update_vbox()

    # -------------------------------------------------------------------------
    # TREE SIGNALS
    # -------------------------------------------------------------------------

    def _connect_workspace_signals(self):
        """
        Connecte les signaux émis par le WorkspaceController à des slots du MainController.
        """
        self.workspace_ctrl.pipeline_changed.connect(self._on_visibility_changed)
        self.workspace_ctrl.analysis_changed.connect(self._on_visibility_changed)
        self.workspace_ctrl.macro_created.connect(self._on_macro_created)

    def _connect_tree_signals(self):
        """
        Connecte les signaux émis par le TreeController à des slots du MainController.
        """

        self.tree_ctrl.item_selected.connect(self.on_item_selected)
        self.tree_ctrl.visibility_changed.connect(self._on_visibility_changed)
        self.tree_ctrl.menu_actions_triggered.connect(self._action_concentrator)

    def _get_attached_item(self,signal):
        
        print(f'Signal {signal} / type {signal.item_type}')

        item_index = self.model.signal_index_map[signal]
        item = item_index.internalPointer()
        return item


    def on_item_selected(self, item: TreeItem|SignalObject|DerivedSignalObject,index = None):
        
        if not isinstance(item,TreeItem):
            item = self._get_attached_item(item)
        
        obj=item.data
        role = item.role
        
        if index is None:
            index = self.model.signal_index_map[obj]
        
        match role:
            case custom_items.itemType.FILE:
                print('file')
                self.param_ctrl.load_params(obj,None,None)

            case custom_items.itemType.RAW:
                
                sel_model = self.view.treefile.selectionModel()
                with QtCore.QSignalBlocker(sel_model):  # ✅ blocage fin et sûr
                    sel_model.setCurrentIndex(  index,
                                                QtCore.QItemSelectionModel.
                                                SelectionFlag.ClearAndSelect
                                                )
                # Mise en évidence de la courbe correspondante
                self.graph_ctrl.highlight(obj)
                # Mise à jour du controleur du curseur (on l'attache à la courbe)
                self.cursor_ctrl.set_signal(obj)
                # Chargement des paramètres dans le parameterTree
                self.param_ctrl.load_params(obj,None,None)
                if self.model.cursor_x is None:
                    #bug si mous_pos = valeur par défaut (voir graph_controller)
                    self.model.updateCursorVal(float(self.graph_ctrl.mouse_pos.x()))
                self.cursor_ctrl.update_x(self.model.cursor_x)
                for file in self.workspace.files:
                    for s in file.signals:
                        s.is_selected = False
                obj.is_selected = True
                # notifier le modèle
                #? pourquoi ne pas faire la notification directement dans le tree_controller ?
                self.model.dataChanged.emit( index, index,[QtCore.Qt.ItemDataRole.FontRole])
                self.view.treefile.viewport().update()

            case custom_items.itemType.FILTER:
                #? est-il utile de passer le parent pour charger le 
                #? sachant que obj = node. L'avantage de la méthode actuelle
                #? réside dans le fait que l'itemTree permet de facilement récupérer
                #? l'ensemble des informations sur la structure de données
                #? à voir s'il n'est pas préférable de changer la méthode 
                #? _on_param_change du parameter_controller
                parent :SignalObject = item.parent.data
                index = parent.pipeline.index(obj)
                self.param_ctrl.load_params(parent, index,None)

            case custom_items.itemType.ANALYSE:
                parent :SignalObject = item.parent.data
                index = parent.analyses.index(obj)
                self.param_ctrl.load_params(parent, None, index)

            case custom_items.itemType.DERIVED:
                parent :SignalObject = item.parent.data
                index = parent.derived_signals.index(obj)
                self.param_ctrl.load_params(parent, None, index)
        '''
        if file is not None:
            #? dans ce cas, on veut éditer les paramètres d'un fichier spécifique
            self.param_ctrl.load_params(file,node_index,analysis_index)
            return
        if node_index is None:
            index = self.model.signal_index_map.get(sig)

            if index is not None:
                sel_model = self.view.treefile.selectionModel()
                with QtCore.QSignalBlocker(sel_model):  # ✅ blocage fin et sûr
                    sel_model.setCurrentIndex( index,
                                            QtCore.QItemSelectionModel.SelectionFlag.ClearAndSelect
                                            )

            # Mise en évidence de la courbe correspondante
            self.graph_ctrl.highlight(sig)
            # Mise à jour du controleur du curseur (on l'attache à la courbe)
            self.cursor_ctrl.set_signal(sig)
            # Chargement des paramètres dans le parameterTree
            self.param_ctrl.load_params(sig,node_index,analysis_index)
            if self.model.cursor_x is None:
                self.model.updateCursorVal(float(self.graph_ctrl.mouse_pos.x()))

            # MAJ du contrôleur du curseur (permet un MAJ du curseur horizontal dès la sélection)
            # d'un signal
            self.cursor_ctrl.update_x(self.model.cursor_x)
            for file in self.workspace.files:
                for s in file.signals:
                    s.is_selected = False
            sig.is_selected = True

            # notifier le modèle
            self.model.dataChanged.emit( index, index,[QtCore.Qt.ItemDataRole.FontRole])
            self.view.treefile.viewport().update()
        elif analysis_index is None:
            print(f'analysis_index is None')
            self.param_ctrl.load_params(sig, node_index,analysis_index)
        else:
            print(f'analysis_index is: {analysis_index}')
            self.param_ctrl.load_params(sig, node_index,analysis_index)'''

    def _on_visibility_changed(self, signal, index=None):
        """
        Un filtre ou une analyse a été ajouté(e) ou modifié(e), il faut mettre à jour la
        courbe correspondante.
        """
        if isinstance(signal,TreeItem):
            sig=signal.data
        else:
            sig=signal
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
        obj = item.data
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
        index = self.model.index(0, 0)
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
        self.menu_ctrl.loadSignal.connect(self.import_ctrl.load_file_dialog)
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
        self.graph_ctrl.curve_selected.connect(self.on_item_selected)
        self.graph_ctrl.cursor_moved_X.connect(self._on_cursor_moved)
        self.graph_ctrl.menu_actions_triggered.connect(self._action_concentrator)


    def _connect_cursor_signals(self):

        # Graph + modèle se mettent à jour quand la logique curseur a calculé y
        self.cursor_ctrl.cursor_moved.connect(self._on_cursor_computed)

    def on_snap_toggled(self, enabled):
        self.cursor_ctrl.set_snap(enabled)

    def _on_cursor_moved(self,x):
        if self.model is None:
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
        self.param_ctrl._params_changed.connect(self._on_param_changed)

    def _on_param_changed(self, signal, filter_index, analysis_index, new_params):
        """
        Slot appelé lorsque l'utilisateur modifie un paramètre dans le ParameterController.
        """


        """Modification des paramètres d'une analyse."""
        if filter_index is None and analysis_index is None:
            print(f'main_controller L350 {new_params}')
            signal.set_params(new_params)
            if isinstance(signal,SignalObject):
                self.graph_ctrl.update_signal(signal)
            else:
                #signal est un FileObject, il faut mettre à jour toutes les courbes associées
                for sig in signal.signals:
                    self.graph_ctrl.update_signal(sig)
            return
        elif filter_index is not None:
            action_type=signal.pipeline[filter_index].action_type
            index=filter_index
        else:
            action_type=signal.analyses[analysis_index].action_type
            index=analysis_index
        self.workspace_ctrl.push(
                                signal,
                                custom_items.ActionRequest(
                                    action_modifier=custom_types.ActionModifier.MODIFY_ACTION,
                                    action_type=action_type,
                                    params=new_params,
                                    index=index
                                    )
                                )
        # Mise à jour de la vue, les paramètres des filtres/analyses sont appliqués dans
        # la logique métier du controller de workspace, il suffit juste de rafraîchir la courbe

        if filter_index is not None:
            self.param_ctrl.load_params(signal,filter_index,None)
        else:
            self.param_ctrl.load_params(signal,None,analysis_index)

    def _on_filter_added(self, sig_item, index,parent_index):
        # retrouver l'index Qt du filtre

        self.tree_ctrl.expand_items(parent_index)
        self._on_visibility_changed(sig_item,index)

    def _on_analysis_added(self,sig_item,index,parent_index):
        
        obj=sig_item.data
        derived_sig=obj.derived_signals[index]
        self.graph_ctrl.add_signal_curve(derived_sig)
        self.tree_ctrl.expand_items(parent_index)
        self.model.signal_index_map[derived_sig] = parent_index

    def _on_filter_changed(self, sig_item, index):

        self.tree_ctrl.expand_items()
        parent_index = self.model.index( sig_item.row(),
                                        0,
                                        self.model.index(   sig_item.parent.row(),
                                                            0,
                                                            QtCore.QModelIndex())
                                        )
        self.tree_ctrl.expand_items(parent_index)
        self._on_visibility_changed(sig_item,index)
        # ajout 09/04 afin de mettre à jour le parameter_tree avec les ctrl-z et y:
        self.param_ctrl.load_params(sig_item.data,index,None)

    # -------------------------------------------------------------------------
    # HELPERS
    # -------------------------------------------------------------------------

    def _current_signal(self):
        """
        Retourne le signal actuellement sélectionné dans la TreeView.
        """
        sel = self.view.treefile.selectionModel().selectedIndexes()
        if not sel:
            return None
        item = sel[0].internalPointer()
        obj = item.data
        if isinstance(obj, SignalObject):
            return obj
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

        # 2) Notifier le modèle (icône + police rouge)
        # Mise à jour ciblée : tous les signaux peuvent être impactés
        for file in self.workspace.files:
            for s in file.signals:
                index = self.model.signal_index_map.get(s)
                if index:
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

        for signal, index in self.model.signal_index_map.items():
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
                print('start recording')
                self.workspace_ctrl.start_macro_recording()
                self.tree_ctrl.macro_recording=True
                self.graph_ctrl.macro_recording=True
                self.tree_ctrl.checkStates(signal)
                self.graph_ctrl.on_selection_changed(signal)
            case custom_types.qSignalType.STOP:
                print('stop recording')
                self.workspace_ctrl.stop_macro_recording()
                self.tree_ctrl.checkStates(signal)
                self.graph_ctrl.on_selection_changed(signal)
            case custom_types.qSignalType.MACRO:
                self.workspace_ctrl.apply_macro(macro_name,signal)
            case _:
                action_request=self._build_action_request(action_type,signal)
                self.workspace_ctrl.push(signal,action_request)


    def _build_action_request(self, action_type, signal):
        """
        Méthode générant les actionRequests nécessaire à la création des Nodes
        filter ou analysis qui puissent être annulées via le undo du workspace controller,
        elle centralise également la logique de demande de paramètres
        (ex: cutoff pour les filtres, signal de référence pour les diff, etc.)

        Args:
            action_type (custom_types.qSignalType): type d'action à réaliser (ajout de filtre,
                                                    ajout d'analyse, etc.)
            signal (SignalObject|DerivedSignalObject): signal concerné par l'action

        Returns:
            custom_items.ActionRequest: structure de données contenant toutes les informations
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
            return custom_items.ActionRequest(
                                                action_modifier =
                                                custom_types.ActionModifier.ADD_ACTION,
                                                action_type = action_type,
                                                params = params,
                                                index = None
                                            )
        #ajout d'un filterNode ou un analaysisNode
        return custom_items.ActionRequest(  action_modifier =
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
                        'order': self.settings["filter_order"]
                        }
            case custom_types.qSignalType.DIFF:
                return {'reference':self.workspace.reference_signal}
            case _ :
                raise AttributeError

    def _on_macro_created(self,macro):

        #! en mettant le RAZ dans cette méthode le soft risque de bloquer la création
        #! des macros dès le premier défaut
        print("fb du workspace on macro created")
        self.tree_ctrl.macro_recording=False
        self.graph_ctrl.macro_recording=False

        self.tree_ctrl.menu.add_macro_action(macro)
        self.graph_ctrl.menu.add_macro_action(macro)


    def quit(self):

        if self.workspace_ctrl is None:
            self.view.close()
        else:
            print(self.workspace_ctrl.undo_stack.count())
            if self.workspace_ctrl.undo_stack.count() >=1:
                self.export_ctrl.save_workspace(self.workspace)
                self.view.close()
            else:
                self.view.close()
