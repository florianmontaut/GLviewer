
# controller/commands/remove_filter.py
from ressources.custom_commands import ReplayableCommand, od_insert, od_remove


class RemoveFilterCommand(ReplayableCommand):
    def __init__(self, signal, model,index):
        """
        Supprime un filtre du pipeline.

        :param signal: SignalObject
        :param index: index du filtre à supprimer
        :param model: PipelineTreeModel
        """
        filter_node = signal.get_filter_by_index(index)
        if filter_node is None:
            raise IndexError(f"No filter at index {index}")
        super().__init__(f"Remove {filter_node.display_name}")

        self.signal = signal
        self.index = index
        self.model = model

        # sauvegarde IMMUTABLE du filtre
        self.removed_filter = filter_node

    # ------------------------------------------
    def redo(self):
        self.signal.pipeline = od_remove(self.signal.pipeline, self.removed_filter.id)
        self.signal.pipeline_version += 1
        # notifier le modèle (TreeView)
        self.model.remove_node(self.signal, self.removed_filter)

    # ------------------------------------------
    def undo(self):
        node = self.removed_filter
        self.signal.pipeline = od_insert(self.signal.pipeline, self.index, node.id, node)
        self.signal.pipeline_version += 1
        # notifier le modèle (TreeView)
        self.model.insert_node(self.signal, node)
