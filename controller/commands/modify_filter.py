
# controller/commands/modify_filter.py
from typing import OrderedDict

from sympy import Order

from ressources.custom_commands import ReplayableCommand


class ModifyFilterCommand(ReplayableCommand):
    def __init__(self, signal, new_params, model,index):
        """
        Modifie les paramètres d'un filtre (par remplacement).

        :param signal: SignalObject
        :param index: index du filtre
        :param new_params: dict des paramètres modifiés
        :param model: PipelineTreeModel
        """
        old_node = list(signal.pipeline.values())[index]
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
    def redo(self):
        """
        self.signal.pipeline[self.index] = self.new_node
        self.signal.invalidate()
        # notifier le modèle (TreeView)
        self.model.update_filter(self.signal, self.index)
        
        """
        items = list(self.signal.pipeline.items())
        new_node = self.new_node
        new_id = new_node.id

        items[self.index] = (new_id, new_node)
        self.signal.pipeline = OrderedDict(items)
        self.signal.pipeline_version += 1

        #! peut être faudra-t-il passer les deux Id (nouveau et ancien)
        self.model.update_node(self.signal, self.index)

        

    # ------------------------------------------
    def undo(self):
        """
        self.signal.pipeline[self.index] = self.old_node
        self.signal.invalidate()
        # notifier le modèle (TreeView)
        self.model.update_filter(self.signal, self.index)

        """
        
        items = list(self.signal.pipeline.items())
        new_id = self.new_node.id
        idx = next(i for i, (fid, _) in enumerate(items) if fid == new_id)

        old_node = self.old_node
        old_id = old_node.id

        items[idx] = (old_id, old_node)
        #! peut être faudra-t-il passer les deux Id (nouveau et ancien)
        self.signal.pipeline = OrderedDict(items)
        self.signal.pipeline_version += 1
        self.model.update_node(self.signal, self.index)
        