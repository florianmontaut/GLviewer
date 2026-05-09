
# controller/parameter_controller.py

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QHeaderView
from pkg_resources import normalize_path
from pyqtgraph.parametertree import Parameter, ParameterTree,parameterTypes
from model.base_objects import SignalObject,FileObject,SelectionContext
from model.filters.base_filter import FilterNode
from model.analysis.base_analysis import AnalysisNode

from ressources.custom_parameters import *


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

    def _on_param_change(self,ctx:SelectionContext):
        """
        Slot appelé lorsque l'utilisateur modifie un paramètre
        dans le ParameterTree.
        """
        if ctx.filter_index is not None:
            node :FilterNode = ctx.signal.pipeline[ctx.filter_index]
        elif ctx.analysis_index is not None:
            node :AnalysisNode = ctx.signal.analyses[ctx.analysis_index]
        else:
            node :SignalObject = ctx.signal

        # 1️⃣ Récupérer les nouvelles valeurs depuis le ParameterTree
        new_params = {}
        for name in node.opts_dict.keys():
            try:
                if isinstance(name,str):
                    new_params[node.opts_dict[name]] = self.param.child(name).value()
                else:
                    new_params[node.opts_dict[name]] = self.param.child(*name).value()
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
        analysis_index: int | None = None'''
        
        sig = ctx.signal
        #! ajouter la gestion des FileObject içi aussi pour pouvoir éditer les paramètres 
        #! globaux du fichier (ex: sampling_rate)
        if ctx.analysis_index is not None:
            #? dans ce cas, on veut éditer les paramètres d'une analyse spécifique
            node = ctx.signal.analyses[ctx.analysis_index]
            if "reference" in node.get_params().keys():
                ext_file=node.get_param('reference').file
                available_signals = [ s for s in ext_file.signals if s is not sig]
            else:
                available_signals = []
        elif ctx.filter_index is not None:
            #? dans ce cas, on veut éditer les paramètres d'un filtre spécifique
            node = sig.pipeline[ctx.filter_index]
            available_signals = [ s for s in sig.file.signals if s is not sig ]
        else:
            #? dans ce cas, on veut éditer les paramètres du signal lui même
            node = sig
            available_signals=[]

        self.param = self.build_parameter_tree_for_object(node, available_signals)
        self.widget.setParameters(self.param, showTop=True)
        #print(f'signal: {sig.name} / index {ctx.filter_index} / analysis index {ctx.analysis_index}')
        self.param.sigTreeStateChanged.connect(
            lambda *_: self._on_param_change(ctx))

        self.widget.header().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)


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
            print(param_name,spec)
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
                #! ne marche pas alors que le même paramètre est passé dans 
                #! graph_option_controller
                param = LinkedCursors(  name = param_name,
                                        graphWidget = self.graph,
                                        cursors_setting = spec["cursors_setting"]
                                        )
                param.setOpts(**spec)
                children.append(param)
                continue
            # -------------
            
            if group_key is None:
                key = obj.opts_dict[param_name]
            else:
                key= obj.opts_dict[group_key + (param_name,)]
            value = obj.get_param(key)
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
            children.append(Parameter.create(**param))


        return Parameter.create(
                                name=name,
                                type="group",
                                children=children
                                )
