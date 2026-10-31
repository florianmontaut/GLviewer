
# controller/commands/file_params.py
import math

from PyQt6.QtGui import QUndoCommand

from model.filters.lowpass import LowPassFilter


class ModifyFileParamsCommand(QUndoCommand):
    """
    Paramètres d'un fichier (période d'échantillonnage, décalage, troncatures,
    étiquette). Les filtres passe-bas réglés sur la période du fichier (fs = 1/période)
    la suivent : ils sont remplacés dans la même commande. Les mises à jour (arbre,
    graphique, analyses) sont faites par le contrôleur (MainController._apply_file_params).
    """

    def __init__(self, controller, file_obj, new_params: dict):
        """ValueError si un filtre ne peut pas suivre la nouvelle période (ex: fréquence
        de coupure supérieure à la moitié de la nouvelle fréquence d'échantillonnage)."""
        super().__init__(f"Modify file {file_obj.name}")
        self.controller = controller
        self.file_obj = file_obj
        self.new_params = dict(new_params)
        self.old_params = {key: file_obj.get_param(key) for key in new_params}
        # (signal, filtre actuel, filtre à la nouvelle période)
        self.filter_swaps = []
        if "sampling" in new_params:
            old_fs, new_fs = 1 / file_obj.sampling, 1 / new_params["sampling"]
            for sig in file_obj.signals:
                for node in sig.pipeline.values():
                    if (isinstance(node, LowPassFilter)
                            and math.isclose(node.get_param("fs"), old_fs, rel_tol=1e-6)):
                        try:
                            new_node = node.clone_with(fs=new_fs)
                        except ValueError as e:
                            raise ValueError(f"{sig.name} : {node.display_name} ne peut pas "
                                             f"suivre la nouvelle période ({e})") from None
                        self.filter_swaps.append((sig, node, new_node))

    def redo(self):
        self.controller._apply_file_params(self.file_obj, self.new_params,
                                           [(s, old, new) for s, old, new in self.filter_swaps])

    def undo(self):
        self.controller._apply_file_params(self.file_obj, self.old_params,
                                           [(s, new, old) for s, old, new in self.filter_swaps])
