from ressources.custom_types import qSignalType,ActionModifier
from model.filters.filter_factory import FilterFactory
from model.analysis.analysis_factory import AnalysisFactory
from controller.commands.add_filter import AddFilterCommand
from controller.commands.remove_filter import RemoveFilterCommand
from controller.commands.modify_filter import ModifyFilterCommand
from controller.commands.add_analysis import AddAnalysisCommand
from controller.commands.remove_analysis import RemoveAnalysisCommand
from controller.commands.modify_analysis import ModifyAnalysisCommand
from ressources.custom_items import ActionRequest,AddDescriptor




# les classes Factory retourne des callables qui sont utilisés dans le workspace_controller
# exemple, la commande est obtenue à l'appelle de la méthode execute de registry
# la clé du dictionnaire est passé par l'actionRequest, qui retourne un callable
# dont les attributs sont forcément sig,params,model et index, eux-mêmes attribut du
# action request. C'est un pointeur de fonctions, dont la création est dynamique (on ne
# créer pas les commandes 1 à 1 à la main)

class AddNodeFactory:

    def __init__(self, node_type, node_factory):
        self.node_type = node_type
        self.node_factory = node_factory

    def __call__(self, sig, params, model, index):
        node = self.node_factory().create({
                                                "type": self.node_type.name,
                                                "params": params
                                                })
        if self.node_factory is FilterFactory:
            return AddFilterCommand(sig, node, model, index)
        else:
            return AddAnalysisCommand(sig, node, model, index)

class ModifyNodeFactory:

    def __init__(self,is_filter:bool):
        self.is_filter=is_filter
        
    def __call__(self, sig, params, model, index):
        if self.is_filter :
            return ModifyFilterCommand(sig, params, model, index)
        else:
            return ModifyAnalysisCommand(sig, params, model, index)

class RemoveNodeFactory:
    def __init__(self,is_filter:bool):
        self.is_filter=is_filter
    def __call__(self, sig, params, model, index):
        if self.is_filter :
            return RemoveFilterCommand(sig, model, index)
        else:
            return RemoveAnalysisCommand(sig, model, index)



class ActionRegistry:

    def __init__(self):
        self._factories = {}
        self._init_action_dict()

    def register(self,  action_modifier: ActionModifier,
                        action_key: qSignalType,
                        factory):
        key = (action_modifier, action_key)
        
        if key in self._factories:
            print(f"⚠️ Overwriting factory for {key}")

        self._factories[(action_modifier,action_key)] = factory

    def execute(self,sig, action_request:ActionRequest):

        key = (action_request.action_modifier, action_request.action_type)
        factory = self._factories.get(key)
        if factory is None:
            raise KeyError(
                            f"No action registered for {action_request.action_modifier=}"+
                            f"{action_request.action_type=}"
                            )

        return factory( sig,
                        action_request.params,
                        action_request.model,
                        action_request.index )


    def _init_action_dict(self):

        for sig_type in (   qSignalType.FILTER, qSignalType.DIFF, qSignalType.AVG,
                            qSignalType.OFFSET, qSignalType.OFFSET_X ):

            # ADD
            self.register(
                            ActionModifier.ADD_ACTION,
                            sig_type,
                            AddNodeFactory(sig_type, FilterFactory)
                            )
            self.register(
                            ActionModifier.REMOVE_ACTION,
                            sig_type,
                            RemoveNodeFactory(True)
                        )
            self.register(
                            ActionModifier.MODIFY_ACTION,
                            sig_type,
                            ModifyNodeFactory(True)
                        )

        for sig_type in (  qSignalType.MODEL, qSignalType.FFT, qSignalType.DIFF_EXT,
                            qSignalType.FORMULA ):
            self.register(
                            ActionModifier.ADD_ACTION,
                            sig_type,
                            AddNodeFactory(sig_type, AnalysisFactory)
                        )
            self.register(
                            ActionModifier.REMOVE_ACTION,
                            sig_type,
                            RemoveNodeFactory(False)
                        )
            self.register(
                            ActionModifier.MODIFY_ACTION,
                            sig_type,
                            ModifyNodeFactory(False)
                        )