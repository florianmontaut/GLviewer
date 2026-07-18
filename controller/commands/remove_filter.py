
# controller/commands/remove_filter.py
from typing import OrderedDict

from ressources.custom_commands import ReplayableCommand


class RemoveFilterCommand(ReplayableCommand):
    def __init__(self, signal, model,index):
        """
        Supprime un filtre du pipeline.

        :param signal: SignalObject
        :param index: index du filtre à supprimer
        :param model: PipelineTreeModel
        """
        filter_node = list(signal.pipeline.values())[index]
        super().__init__(f"Remove {filter_node.display_name}")

        self.signal = signal
        self.index = index
        self.model = model

        # sauvegarde IMMUTABLE du filtre
        self.removed_filter = filter_node

    # ------------------------------------------
    def redo(self):
        """
        self.signal.pipeline.pop(self.index)
        self.signal.invalidate()
        # notifier le modèle (TreeView)
        self.model.remove_filter(self.signal, self.index)
        
        """
        
        items = list(self.signal.pipeline.items()) 

        f_id, self.removed_filter = items.pop(self.index)
        self.signal.pipeline = OrderedDict(items)
        self.signal.pipeline_version += 1
        self.model.remove_filter(self.signal, self.index)

        

    # ------------------------------------------
    def undo(self):
        
        """
        self.signal.pipeline.insert(self.index, self.removed_filter)
        self.signal.invalidate()
        # notifier le modèle (TreeView)
        self.model.insert_filter(self.signal,self.removed_filter, self.index)
        """

        items = list(self.signal.pipeline.items())

        f_id = self.removed_filter.id
        items.insert(self.index, (f_id, self.removed_filter))
        self.signal.pipeline = OrderedDict(items)
        self.signal.pipeline_version += 1
        self.model.insert_filter(self.signal, self.removed_filter, self.index)
