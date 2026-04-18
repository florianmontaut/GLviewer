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

class ActionRegistry:

    def __init__(self):
        self._factories = {}
        self._init_action_dict()

    def register(self,  action_modifier: ActionModifier,
                        action_key: qSignalType,
                        factory):
        self._factories[(action_modifier,action_key)] = factory

    def execute(self,sig, action_request:ActionRequest):

        key = (action_request.action_modifier, action_request.action_type)
        try:
            factory = self._factories.get(key)
        except KeyError:
            raise KeyError(
                            f"No action registered for {action_request.action_modifier=}"+
                            f"{action_request.action_type=}"
                            )

        return factory( sig,
                        action_request.params,
                        action_request.model,
                        action_request.index )


    def _init_action_dict(self):


        for sig_type in (   qSignalType.FILTER,
                            qSignalType.DIFF,
                            qSignalType.OFFSET,
                            qSignalType.OFFSET_X,
                        ):

            # ADD
            self.register(
                        ActionModifier.ADD_ACTION,
                        sig_type,
                        lambda  sig,
                                params,
                                model,
                                index,
                                st=sig_type: AddFilterCommand(
                                                                sig,
                                                                FilterFactory().create(
                                                                    {
                                                                    'type':st.name,
                                                                    "params": params
                                                                    }),
                                                                model,
                                                                index
                                                            )
                        )
            # REMOVE
            self.register(
                        ActionModifier.REMOVE_ACTION,
                        sig_type,
                        lambda  sig,
                                params,
                                model,
                                index,
                                st=sig_type: RemoveFilterCommand(
                                                                    sig,
                                                                    model,
                                                                    index
                                                                )
                        )
            # Modify
            self.register(
                        ActionModifier.MODIFY_ACTION,
                        sig_type,
                        lambda  sig,
                                params,
                                model,
                                index,
                                st=sig_type: ModifyFilterCommand(
                                                                    sig,
                                                                    params,
                                                                    model,
                                                                    index
                                                                )
                        )

        for sig_type in (   qSignalType.MODEL,
                            qSignalType.FFT
                        ):

            # ADD
            self.register(
                            ActionModifier.ADD_ACTION,
                            sig_type,
                            lambda  sig,
                                    params,
                                    model,
                                    index,
                                    st=sig_type: AddAnalysisCommand(
                                                                    sig,
                                                                    AnalysisFactory().create(
                                                                        {
                                                                            'type':st.name,
                                                                            'params':params
                                                                        }),
                                                                    model,
                                                                    index
                                                                    )
                        )
            # REMOVE
            self.register(
                            ActionModifier.REMOVE_ACTION,
                            sig_type,
                            lambda  sig,
                                    params,
                                    model,
                                    index,
                                    st=sig_type: RemoveAnalysisCommand(
                                                                            sig,
                                                                            model,
                                                                            index
                                                                        )
                        )
            # Modify
            self.register(
                            ActionModifier.MODIFY_ACTION,
                            sig_type,
                            lambda  sig,
                                    params,
                                    model,
                                    index,
                                    st=sig_type: ModifyAnalysisCommand(
                                                                            sig,
                                                                            params,
                                                                            model,
                                                                            index
                                                                        )
                        )
