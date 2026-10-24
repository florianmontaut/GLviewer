
# model/annotations.py

import uuid
from dataclasses import dataclass, field, replace


@dataclass(frozen=True)
class TextAnnotation:
    """
    Texte ajouté sur le graphique (modèle). Immutable comme les FilterNode / AnalysisNode :
    une modification crée une nouvelle instance (dataclasses.replace) de même id, ce qui
    permet aux commandes undo/redo de conserver l'ancien et le nouvel état.

        html        : contenu (police, couleurs... tels que saisis dans l'éditeur)
        pos         : position du texte, coordonnées des données (x, y)
        anchor_pos  : point annoté relié au texte par une flèche (x, y), ou None
        color       : couleur par défaut du texte et couleur de la flèche (#AARRGGBB)
        font        : police par défaut du texte (QFont.toString())
    """
    html:       str
    pos:        tuple[float, float]
    anchor_pos: tuple[float, float] | None = None
    color:      str = "#ff000000"
    font:       str = ""
    id:         str = field(default_factory=lambda: uuid.uuid4().hex)

    def with_changes(self, **changes) -> "TextAnnotation":
        return replace(self, **changes)

    def to_dict(self) -> dict:
        return {
                "id"            : self.id,
                "html"          : self.html,
                "pos"           : list(self.pos),
                "anchor_pos"    : None if self.anchor_pos is None else list(self.anchor_pos),
                "color"         : self.color,
                "font"          : self.font,
                }

    @staticmethod
    def from_dict(data: dict) -> "TextAnnotation":
        anchor = data.get("anchor_pos")
        return TextAnnotation(
                                html        = data.get("html", ""),
                                pos         = tuple(data["pos"]),
                                anchor_pos  = None if anchor is None else tuple(anchor),
                                color       = data.get("color", "#ff000000"),
                                font        = data.get("font", ""),
                                id          = data.get("id") or uuid.uuid4().hex,
                            )
