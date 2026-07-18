from typing import OrderedDict

from ressources.custom_commands import ReplayableCommand
from ressources.custom_items import AddDescriptor
from ressources.custom_types import ActionModifier

class AddAnalysisCommand(ReplayableCommand):
    """Ajoute une analyse à un signal."""

    def __init__(self, signal, analysis_node, model, index=None):
        """
        :param signal: SignalObject
        :param analysis_node: AnalysisNode instance
        :param model: PipelineTreeModel
        :param index: position dans la liste analyses (None = append)
        """
        super().__init__(f"Add {analysis_node.display_name}")

        self.signal = signal
        self.analysis_node = analysis_node
        self.model = model
        self.index = index
        self.error = None
        self.derived_signal = None  # sera créé en redo()



    def prepare(self):
        if self.index is None:
            self.index = len(self.signal.analyses.values())
        self.derived_signal = self.analysis_node.compute(self.signal)

    def redo(self):
        """
        # Ajouter l'analyse
        self.signal.analyses.insert(self.index, self.analysis_node)
        """
        # Calculer et ajouter le signal dérivé
        '''try:
            self.derived_signal = self.analysis_node.compute(self.signal)
            self.signal.derived_signals.append(self.derived_signal)
        
        except Exception as e:
            self.signal.analyses.pop(self.index)
            self.error = e
            return
            '''
        node = self.analysis_node
        aid = node.id
    
        items = list(self.signal.analyses.items())
    
        if self.index is None:
            items.append((aid, node))
            self.index = len(items) - 1
        else:
            items.insert(self.index, (aid, node))
    
        self.signal.analyses = OrderedDict(items)
        self.model.insert_analysis(self.signal, node, self.index)

    def undo(self):
        items = list(self.signal.analyses.items())
    
        items.pop(self.index)
        self.signal.analyses = OrderedDict(items)
        self.model.remove_analysis(self.signal, self.index)

