
# controller/parameter_controller.py

from PyQt6.QtCore import QObject, pyqtSignal, QTimer
from PyQt6.QtWidgets import QHeaderView
from pyqtgraph.parametertree import Parameter, ParameterTree,parameterTypes
from model.base_objects import SignalObject,FileObject
from model.filters.base_filter import FilterNode
from model.analysis.base_analysis import AnalysisNode

from ressources.custom_parameters import *
from ressources.custom_items import SelectionContext


class ParameterController(QObject):
    """
    Gère la ParameterTree :
    - paramètres du signal (color, visible, width)
    - paramètres du filtre sélectionné
    """

    #? Signaux émis quand les paramètres sont modifiés:
    #   Signal/ index du filtre ou None/ index de l'analyse ou None/ nouveaux paramètres
    params_changed = pyqtSignal(SelectionContext, dict)

    def __init__(self, param_widget: ParameterTree, graph_widget):
        super().__init__()
        self.widget = param_widget
        self.graph = graph_widget
        self.param = None
        # connexion du ParameterTree affiché (déconnectée à chaque reconstruction afin
        # que l'ancien arbre ne puisse plus émettre avec un SelectionContext périmé)
        self._tree_slot = None
        # (min, max) des abscisses du signal affiché : position des curseurs d'une plage
        # non définie (None)
        self._data_range = None
        # affichage des curseurs conservé d'un arbre à l'autre (ex: après un recalcul)
        self._cursors_shown = {}

    def _on_param_change(self,ctx:SelectionContext):
        """
        Slot appelé lorsque l'utilisateur modifie un paramètre
        dans le ParameterTree.
        """
        if ctx.filter_id is not None:
            node : FilterNode = ctx.get_filter()
        elif ctx.analysis_id is not None:
            node : AnalysisNode = ctx.get_analysis()
        else:
            node : SignalObject = ctx.signal

        # 1️⃣ Récupérer les nouvelles valeurs depuis le ParameterTree
        new_params = {}
        for name in node.opts_dict.keys():
            try:
                if isinstance(name,str):
                    child = self.param.child(name)
                else:
                    child = self.param.child(*name)
                if isinstance(child, LinkedCursors):
                    # plage [début, fin] (value() renvoie le détail des curseurs)
                    new_params[node.opts_dict[name]] = child.positions()
                else:
                    new_params[node.opts_dict[name]] = child.value()
            except Exception as e:
                # Paramètre absent ou non éditable
                print(f"Erreur lors de la récupération du paramètre '{name}': {e}")
                continue

        # 2️⃣ Ne rien faire si aucun changement réel
        if new_params == node.get_params():
            return

        # 3️⃣ Émettre un signal avec les nouveaux paramètres
        self.params_changed.emit(
                                    ctx,
                                    new_params
                                )


    def load_params(self, ctx = SelectionContext):   

        '''sig: SignalObject|FileObject,
        index: int|None = None,
        analysis_id: int | None = None'''
        
        sig = ctx.signal
        #! ajouter la gestion des FileObject içi aussi pour pouvoir éditer les paramètres 
        #! globaux du fichier (ex: sampling_rate)
        node = ctx.get_node()
        if ctx.analysis_id is not None:
            #? dans ce cas, on veut éditer les paramètres d'une analyse spécifique
            if "reference" in node.get_params().keys():
                ext_file=node.get_param('reference').file
                available_signals = [ s for s in ext_file.signals if s is not sig]
            else:
                available_signals = []
        elif ctx.filter_id is not None:
            #? dans ce cas, on veut éditer les paramètres d'un filtre spécifique
            available_signals = [ s for s in sig.file.signals if s is not sig ]
        else:
            #? dans ce cas, on veut éditer les paramètres du signal lui même
            available_signals=[]

        self._clear_param_tree()
        # signal du contexte : conversion des valeurs affichées (ex: plage d'un modèle)
        self._signal = sig
        x = getattr(sig, 'x', None)
        self._data_range = (float(x[0]), float(x[-1])) if x is not None and len(x) else None

        self.param = self.build_parameter_tree_for_object(node, available_signals)
        self.widget.setParameters(self.param, showTop=True)
        #print(f'signal: {sig.name} / index {ctx.filter_id} / analysis index {ctx.analysis_id}')
        self._tree_slot = lambda param, changes: self._on_tree_changed(ctx, changes)
        self.param.sigTreeStateChanged.connect(self._tree_slot)
        for cursors in self._linked_cursors(self.param):
            # la plage n'est appliquée qu'à la fin du déplacement d'un curseur. Différé :
            # le recalcul reconstruit l'arbre et retire les curseurs, ce qui ne doit pas
            # se faire pendant l'événement souris du curseur lui-même
            cursors.sigRangeCommitted.connect(
                    lambda _: QTimer.singleShot(0, lambda: self._on_param_change(ctx)))

        self.widget.header().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)


    def clear(self):
        """Plus rien à afficher (ex: fichier retiré)."""
        self._clear_param_tree()
        self.param = None
        self._signal = None
        self.widget.clear()

    def shows(self, file_obj) -> bool:
        """Les paramètres affichés concernent-ils ce fichier (ou l'une de ses voies) ?"""
        sig = getattr(self, "_signal", None)
        return sig is file_obj or getattr(sig, "file", None) is file_obj

    @staticmethod
    def _linked_cursors(param):
        """LinkedCursors présents dans un arbre de paramètres."""
        if isinstance(param, LinkedCursors):
            yield param
            return
        for child in param.children():
            yield from ParameterController._linked_cursors(child)

    def _clear_param_tree(self):
        """Déconnecte l'arbre affiché et retire ses curseurs du graphique."""
        if self.param is None:
            return
        if self._tree_slot is not None:
            self.param.sigTreeStateChanged.disconnect(self._tree_slot)
            self._tree_slot = None
        for cursors in self._linked_cursors(self.param):
            self._cursors_shown[cursors.name()] = cursors.param('show cursors').value()
            cursors.sigRangeCommitted.disconnect()
            cursors.remove_from_graph()

    def _on_tree_changed(self, ctx: SelectionContext, changes):
        """
        Modification dans le ParameterTree. Les changements internes aux curseurs
        (affichage, déplacement, delta) sont ignorés : la plage est appliquée par
        sigRangeCommitted, une seule fois en fin de déplacement.
        """
        def in_cursors(param):
            while param is not None:
                if isinstance(param, LinkedCursors):
                    return True
                param = param.parent()
            return False

        if all(in_cursors(param) for param, _, _ in changes):
            return
        self._on_param_change(ctx)

    def _on_action_triggered(self,action):
        """
            Slot appelé lorsque l'utilisateur clique sur un bouton
            d'action dans le ParameterTree.
        """
        print(action)

    def build_parameter_tree_for_object(self,obj, available_signals):
        return self._build_parameter_group(
                                            name=obj.display_name,
                                            schema=obj.PARAMETER_SCHEMA,
                                            obj=obj,
                                            available_signals=available_signals
                                            )

    def _build_parameter_group( self,
                                name: str,
                                schema: dict,
                                obj,
                                available_signals,
                                group_key=None
                                ):
        
        children = []

        for param_name, spec in schema.items():
            ptype = spec["type"]
            #la valeur actuelle sauvegardée dans le filter node est récupérée içi
            # ---------- GROUP ----------
            #print(param_name,spec)
            if ptype == "group":
                # permet de construire récursivement les groupes imbriqués
                if group_key is not None:
                    obj_key = group_key + (param_name,)
                else:
                    obj_key = (param_name,)
                group = self._build_parameter_group(
                                                    name=param_name,
                                                    schema=spec.get("children", {}),
                                                    obj=obj,
                                                    available_signals=available_signals,
                                                    group_key=obj_key
                                                    )
                group.setOpts(
                                expanded=spec.get("expanded", False)
                            )
                children.append(group)
                continue
            
            # ------------- paramètres custom complexes n'ayant pas de valeur propre------------
            if ptype == "complementary":
                param["expanded"] = True

                param = ComplementaryElements(
                                                name=param_name,
                                                start=spec.get("start_x",0),
                                                stop=spec.get("stop_x",1)
                                            )
                children.append(param)
                continue
            
            if ptype == "cursors":
                # plage [début, fin] stockée dans le node, à défaut l'ensemble du signal
                key = obj.opts_dict[param_name if group_key is None
                                    else group_key + (param_name,)]
                if hasattr(obj, 'display_param'):
                    value = obj.display_param(key, self._signal)
                else:
                    value = obj.get_param(key)
                value = value or self._data_range or spec["cursors_setting"]["pos"]
                cursors_setting = dict(spec["cursors_setting"], pos=list(value))
                param = LinkedCursors(  name = param_name,
                                        graphWidget = self.graph,
                                        cursors_setting = cursors_setting,
                                        expanded = spec.get("expanded", False),
                                        show = self._cursors_shown.get(param_name,
                                                                    spec.get("visible", False))
                                        )
                children.append(param)
                continue
            # -------------
            
            if group_key is None:
                key = obj.opts_dict[param_name]
            else:
                key= obj.opts_dict[group_key + (param_name,)]
            value = obj.get_param(key)
            # -----------------------------
            # Voie du fichier (ex: source de la puissance d'un modèle) : nom affiché, id
            # enregistré ; valeur "" = saisie manuelle
            # -----------------------------
            if ptype == "channel":
                file_obj = getattr(self._signal, "file", None)
                signals = [s for s in getattr(file_obj, "signals", [])
                           if s is not self._signal]
                limits = {spec.get("manual_label", "Manual value"): ""}
                limits.update({s.name: s.id for s in signals})
                by_name = {s.name: s.id for s in signals}
                if value in by_name and value not in limits.values():
                    value = by_name[value]      # projet d'avant l'id : voie par son nom
                elif value and value not in limits.values():
                    # voie supprimée : reste affichée (le modèle est signalé ⚠)
                    limits["Voie introuvable"] = value
                param = parameterTypes.ListParameter(name=param_name, limits=limits,
                                                     value=value or "",
                                                     tip=spec.get("description"))
                children.append(param)
                continue
            # -----------------------------
            # Signal selector (ComboBox)
            # -----------------------------
            if ptype == "signal":
                value = obj.get_param(key)
                sig_map = { sig.name: sig for sig in available_signals  }
                param = parameterTypes.ListParameter(
                                                        name=param_name,
                                                        values=sig_map,
                                                        value=value,
                                                        limits=list(sig_map.values())
                                                    )
                children.append(param)
                continue
            # ---------- ACTION ----------
            if ptype == "action":
                param = Parameter.create( name=param_name,type="action")
                param.sigActivated.connect(lambda x = param_name:
                                            self._on_action_triggered(x))
                children.append(param)
                continue

            # ---------- CUSTOM ELEMENTS ----------
            #! à améliorer : la gestion des éléments personnalisés (ex: complementary) est un peu bancale,
            #! il faudrait trouver une manière plus élégante de les intégrer dans le système de paramètres

            # ---------- PEN ----------
            if ptype == "pen":
                param["expanded"] = True
            # ---------- SIMPLE TYPES ----------
            param = {
                        "name":     param_name,
                        "value":    value
                    }
            # Nettoyage
            param = {k: v for k, v in param.items() if v is not None}
            param.update(spec)
            # valeur rétablie par le bouton de réinitialisation, propre à l'objet (ex:
            # période d'échantillonnage lue à l'import du fichier)
            if hasattr(obj, "param_default") and obj.param_default(key) is not None:
                param["default"] = obj.param_default(key)
            children.append(Parameter.create(**param))


        return Parameter.create(
                                name=name,
                                type="group",
                                children=children
                                )
