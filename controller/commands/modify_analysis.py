from ressources.custom_commands import ReplayableCommand, od_replace


class ModifyAnalysisCommand(ReplayableCommand):
    """Modifie les paramètres d'une analyse et recalcule ses résultats."""

    def __init__(self, signal, new_params, model,index):
        """
        :param signal: SignalObject
        :param index: index de l'analyse
        :param new_params: dict des paramètres modifiés
        :param model: PipelineTreeModel
        """
        old_node = signal.get_analysis_by_index(index)
        if old_node is None:
            raise IndexError(f"No analysis at index {index}")
        new_node = old_node.clone_with(**new_params)

        super().__init__(f"Modify {old_node.display_name} → {new_node.display_name}")

        self.signal = signal
        self.index = index
        self.model = model

        self.old_node = old_node
        self.new_node = new_node

        self.old_derived = [
                            ds for ds in signal.derived_signals
                            if hasattr(ds, 'metadata') and
                            ds.metadata.get('analysis_id') == old_node.id
                            ]
        self.new_derived = None  # calculé par prepare()

    def prepare(self):
        """Recalcul de l'analyse AVANT le push (voir AddAnalysisCommand.prepare)."""
        self.new_derived = [self.new_node.derive(self.signal)]

    def _swap(self, old, new, old_derived, new_derived):
        self.signal.analyses = od_replace(self.signal.analyses, old.id, new.id, new)
        # par id : les signaux dérivés ont pu être recalculés (SignalObject.refresh_derived)
        for ds in [ds for ds in self.signal.derived_signals
                   if ds.metadata.get('analysis_id') == old.id]:
            self.signal.derived_signals.remove(ds)
        self.signal.derived_signals.extend(new_derived)
        self.model.replace_node(self.signal, old, new)

    def redo(self):
        if self.new_derived is None:
            self.prepare()
        self._swap(self.old_node, self.new_node, self.old_derived, self.new_derived)

    def undo(self):
        self._swap(self.new_node, self.old_node, self.new_derived, self.old_derived)
