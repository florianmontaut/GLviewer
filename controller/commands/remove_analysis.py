from ressources.custom_commands import ReplayableCommand, od_insert, od_remove


class RemoveAnalysisCommand(ReplayableCommand):
    """Supprime une analyse d'un signal."""

    def __init__(self, signal, model, index):
        """
        :param signal: SignalObject
        :param index: index de l'analyse à supprimer
        :param model: PipelineTreeModel
        """
        analysis_node = signal.get_analysis_by_index(index)
        if analysis_node is None:
            raise IndexError(f"No analysis at index {index}")
        super().__init__(f"Remove {analysis_node.display_name}")

        self.signal = signal
        self.index = index
        self.model = model

        # Sauvegarde IMMUTABLE de l'analyse et ses dérivés
        self.removed_analysis = analysis_node
        # Identifie les derived signals liés (par métadonnées)
        self.removed_derived = [
                                    ds for ds in signal.derived_signals
                                    if hasattr(ds, 'metadata') and
                                    ds.metadata.get('analysis_id') == analysis_node.id
                                ]

    def redo(self):
        self.signal.analyses = od_remove(self.signal.analyses, self.removed_analysis.id)
        # Supprimer les signaux dérivés associés
        for ds in self.removed_derived:
            if ds in self.signal.derived_signals:
                self.signal.derived_signals.remove(ds)

        self.model.remove_node(self.signal, self.removed_analysis)

    def undo(self):
        node = self.removed_analysis
        self.signal.analyses = od_insert(self.signal.analyses, self.index, node.id, node)
        self.signal.derived_signals.extend(self.removed_derived)
        self.model.insert_node(self.signal, node)
