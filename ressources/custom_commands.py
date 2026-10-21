
from collections import OrderedDict

from PyQt6.QtGui import QUndoCommand

class ReplayableCommand(QUndoCommand):

    def __init__(self,text=""):
        super().__init__(text)
        self.error = None

    def to_descriptor(self):
        raise NotImplementedError


# ----------------------------------------------------------------------
# Helpers OrderedDict (signal.pipeline / signal.analyses : id -> node)
# Les commandes identifient les nodes par leur id, la position (index) n'est
# utilisée que pour réinsérer un node au même endroit lors d'un undo.
# ----------------------------------------------------------------------

def od_insert(ordered: OrderedDict, index: int, key, value) -> OrderedDict:
    """Retourne une copie de ordered avec (key, value) inséré à la position index."""
    items = list(ordered.items())
    items.insert(index, (key, value))
    return OrderedDict(items)

def od_remove(ordered: OrderedDict, key) -> OrderedDict:
    """Retourne une copie de ordered sans la clé key."""
    return OrderedDict((k, v) for k, v in ordered.items() if k != key)

def od_replace(ordered: OrderedDict, old_key, new_key, value) -> OrderedDict:
    """Retourne une copie de ordered où old_key est remplacé par (new_key, value),
    à la même position."""
    return OrderedDict(
                        (new_key, value) if k == old_key else (k, v)
                        for k, v in ordered.items()
                    )
