from typing import OrderedDict

from ressources.custom_commands import ReplayableCommand


class ModifyAnalysisCommand(ReplayableCommand):
    """Modifie les paramètres d'une analyse et recalcule ses résultats."""

    def __init__(self, signal, new_params, model,index):
        """
        :param signal: SignalObject
        :param index: index de l'analyse
        :param new_params: dict des paramètres modifiés
        :param model: PipelineTreeModel
        """
        old_node = signal.analyses[index]
        new_node = old_node.clone_with(**new_params)

        super().__init__(f"Modify {old_node.display_name} → {new_node.display_name}")

        self.signal = signal
        self.index = index
        self.model = model

        self.old_node = old_node
        self.new_node = new_node

        # Précalculer les dérivés pour redo/undo rapide
        self.old_derived = None
        self.new_derived = None

    def redo(self):
        # Sauvegarder les anciens dérivés (lazy)
        '''
        if self.old_derived is None:
            self.old_derived = [
                                ds for ds in self.signal.derived_signals
                                if hasattr(ds, 'metadata') and
                                ds.metadata.get('analysis_id') == self.old_node.id
                                ]

        # Remplacer l'analyse
        self.signal.analyses[self.index] = self.new_node

        # Recalculer les dérivés
        try:
            self.new_derived = self.new_node.compute(self.signal)

            # Remplacer les anciens dérivés
            for old_ds in self.old_derived:
                if old_ds in self.signal.derived_signals:
                    self.signal.derived_signals.remove(old_ds)

            self.signal.derived_signals.append(self.new_derived)
        except Exception as e:
            # rollback
            self.signal.analyses[self.index] = self.old_node
            raise RuntimeError(f"Analysis recompute failed: {e}")

        self.model.update_analysis(self.signal, self.index)

        '''
        
        items = list(self.signal.analyses.items())

        old_id, _ = items[self.index]

        new_node = self.new_node
        new_id = new_node.id

        items[self.index] = (new_id, new_node)

        self.signal.analyses = OrderedDict(items)
        self.model.update_analysis(self.signal, self.index)
        
            
        
        
        
        
    def undo(self):
        '''
        self.signal.analyses[self.index] = self.old_node

        # Restaurer les anciens dérivés
        if self.new_derived in self.signal.derived_signals:
            self.signal.derived_signals.remove(self.new_derived)

        self.signal.derived_signals.extend(self.old_derived)

        self.model.update_analysis(self.signal, self.index)
        
        '''
        items = list(self.signal.analyses.items())

        new_id = self.new_node.id
        idx = next(i for i, (aid, _) in enumerate(items) if aid == new_id)

        old_node = self.old_node
        old_id = old_node.id

        items[idx] = (old_id, old_node)

        self.signal.analyses = OrderedDict(items)

        self.model.update_analysis(self.signal, self.index)
        