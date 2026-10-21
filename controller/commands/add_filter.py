
# controller/commands/add_filter.py
from ressources.custom_commands import ReplayableCommand, od_insert, od_remove

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
        # position finale fixée dès la création : WorkspaceController l'utilise
        # après le push pour construire le SelectionContext
        self.index = len(signal.pipeline) if index is None else index

    # ------------------------------------------
    def redo(self):
        node = self.filter_node
        self.signal.pipeline = od_insert(self.signal.pipeline, self.index, node.id, node)
        self.signal.pipeline_version += 1
        # notifier le modèle (TreeView)
        self.model.insert_node(self.signal, node)

    # ------------------------------------------
    def undo(self):
        self.signal.pipeline = od_remove(self.signal.pipeline, self.filter_node.id)
        self.signal.pipeline_version += 1
        # notifier le modèle (TreeView)
        self.model.remove_node(self.signal, self.filter_node)
