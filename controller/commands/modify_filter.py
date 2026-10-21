
# controller/commands/modify_filter.py
from ressources.custom_commands import ReplayableCommand, od_replace


class ModifyFilterCommand(ReplayableCommand):
    def __init__(self, signal, new_params, model,index):
        """
        Modifie les paramètres d'un filtre (par remplacement).

        :param signal: SignalObject
        :param index: index du filtre
        :param new_params: dict des paramètres modifiés
        :param model: PipelineTreeModel
        """
        old_node = signal.get_filter_by_index(index)
        if old_node is None:
            raise IndexError(f"No filter at index {index}")
        # clone_with valide les paramètres : une erreur remonte avant le push
        new_node = old_node.clone_with(**new_params)

        super().__init__(
            f"Modify {old_node.display_name} → {new_node.display_name}"
        )

        self.signal = signal
        self.index = index
        self.model = model

        self.old_node = old_node
        self.new_node = new_node

    # ------------------------------------------
    def _swap(self, old, new):
        self.signal.pipeline = od_replace(self.signal.pipeline, old.id, new.id, new)
        self.signal.pipeline_version += 1
        # notifier le modèle (TreeView)
        self.model.replace_node(self.signal, old, new)

    def redo(self):
        self._swap(self.old_node, self.new_node)

    def undo(self):
        self._swap(self.new_node, self.old_node)
