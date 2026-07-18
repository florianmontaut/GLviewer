from typing import OrderedDict

from ressources.custom_commands import ReplayableCommand


class RemoveAnalysisCommand(ReplayableCommand):
    """Supprime une analyse d'un signal."""

    def __init__(self, signal, model, index):
        """
        :param signal: SignalObject
        :param index: index de l'analyse à supprimer
        :param model: PipelineTreeModel
        """
        
        analysis_node = signal.analyses[index]
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
        '''
        self.signal.analyses.pop(self.index)

        # Supprimer les signaux dérivés associés
        for ds in self.removed_derived:
            if ds in self.signal.derived_signals:
                self.signal.derived_signals.remove(ds)
                
        '''
        
        items = list(self.signal.analyses.items())

        a_id, self.removed_analysis = items.pop(self.index)
        self.signal.analyses = OrderedDict(items)
        self.model.remove_analysis(self.signal, self.index)

    def undo(self):
        '''
        self.signal.analyses.insert(self.index, self.removed_analysis)
        self.signal.derived_signals.extend(self.removed_derived)
        self.model.insert_analysis(self.signal, self.removed_analysis, self.index)
        
        '''
        
        items = list(self.signal.analyses.items())
        a_id = self.removed_analysis.id
        items.insert(self.index, (a_id, self.removed_analysis))
        self.signal.analyses = OrderedDict(items)
        self.model.insert_analysis(self.signal, self.removed_analysis, self.index)
        
        
