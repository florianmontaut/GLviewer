from ressources.custom_commands import ReplayableCommand, od_insert, od_remove

class AddAnalysisCommand(ReplayableCommand):
    """Ajoute une analyse à un signal."""

    def __init__(self, signal, analysis_node, model, index=None):
        """
        :param signal: SignalObject
        :param analysis_node: AnalysisNode instance
        :param model: PipelineTreeModel
        :param index: position dans les analyses (None = append)
        """
        super().__init__(f"Add {analysis_node.display_name}")

        self.signal = signal
        self.analysis_node = analysis_node
        self.model = model
        self.index = len(signal.analyses) if index is None else index
        self.derived_signal = None  # calculé par prepare()

    def prepare(self):
        """
        Calcul de l'analyse, appelé par le WorkspaceController AVANT le push :
        redo() est appelé par Qt (QUndoStack.push) et une exception y serait
        perdue. Si le calcul échoue, la commande n'est jamais empilée.
        """
        self.derived_signal = self.analysis_node.derive(self.signal)

    def redo(self):
        if self.derived_signal is None:
            self.prepare()
        node = self.analysis_node
        self.signal.analyses = od_insert(self.signal.analyses, self.index, node.id, node)
        self.signal.derived_signals.append(self.derived_signal)
        # notifier le modèle (TreeView)
        self.model.insert_node(self.signal, node)

    def undo(self):
        node = self.analysis_node
        self.signal.analyses = od_remove(self.signal.analyses, node.id)
        # par id : le signal dérivé a pu être recalculé (SignalObject.refresh_derived)
        for ds in [ds for ds in self.signal.derived_signals
                   if ds.metadata.get('analysis_id') == node.id]:
            self.signal.derived_signals.remove(ds)
        # notifier le modèle (TreeView)
        self.model.remove_node(self.signal, node)
