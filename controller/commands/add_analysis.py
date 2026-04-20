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
        self.derived_signal = None  # sera créé en redo()

    def redo(self):
        if self.index is None:
            self.index = len(self.signal.analyses)
        # Ajouter l'analyse
        self.signal.analyses.insert(self.index, self.analysis_node)

        # Calculer et ajouter le signal dérivé
        try:
            self.derived_signal = self.analysis_node.compute(self.signal)
            self.signal.derived_signals.append(self.derived_signal)
        except Exception as e:
            # rollback si computation échoue
            self.signal.analyses.pop(self.index)
            raise RuntimeError(f"Analysis computation failed: {e}")

        # Notifier le modèle (TreeView)
        self.model.insert_analysis(self.signal, self.analysis_node, self.index)

    def undo(self):
        self.signal.analyses.pop(self.index)
        if self.derived_signal in self.signal.derived_signals:
            self.signal.derived_signals.remove(self.derived_signal)

        self.model.remove_analysis(self.signal, self.index)

