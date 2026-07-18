
# controller/commands/add_filter.py
from typing import OrderedDict

from ressources.custom_commands import ReplayableCommand
from ressources.custom_items import AddDescriptor
from ressources.custom_types import ActionModifier

class AddFilterCommand(ReplayableCommand):

    def __init__(self, signal, filter_node, model, index=None):
        """
        Ajoute un filtre au pipeline d'un signal.

        :param signal: SignalObject
        :param filter_node: FilterNode (immutable)
        :param model: PipelineTreeModel
        :param index: position dans le pipeline (None = append)
        """
        super().__init__(f"Add {filter_node.display_name}")

        self.signal = signal
        self.filter_node = filter_node
        self.model = model
        self.index = index

    # ------------------------------------------
    def redo(self):
        '''
        
        if self.index is None:
            self.index = len(self.signal.pipeline)-1 if len(self.signal.pipeline)>0 else 0
        self.signal.pipeline.insert(self.index, self.filter_node)
        self.signal.invalidate()
        
        self.signal.pipeline_version += 1
        
        # notifier le modèle (TreeView)
        self.model.insert_filter(self.signal, self.filter_node, self.index)
        
        
        '''
        
        filter_id = self.filter_node.id
        items = list(self.signal.pipeline.values())
        if self.index is None:
            items.append((filter_id, self.filter_node))
            self.index = len(items) - 1
        else:
            items.insert(self.index, (filter_id, self.filter_node))
        self.signal.pipeline = OrderedDict(items)
        self.signal.pipeline_version += 1
        self.model.insert_filter(self.signal, self.filter_node, self.index)
        
        

    # ------------------------------------------
    def undo(self):
        '''
        self.signal.pipeline.pop(self.index)
        self.signal.invalidate()
        
        # notifier le modèle (TreeView)
        self.model.remove_filter(self.signal, self.index)
        '''
        items = list(self.signal.pipeline.items())

        # supprime l'élément inséré
        items.pop(self.index)
        self.signal.pipeline = OrderedDict(items)
        self.signal.pipeline_version += 1
        self.model.remove_filter(self.signal, self.index)
        