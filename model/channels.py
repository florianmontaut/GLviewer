
# model/channels.py
"""
Vue « Par voie » : appariement des voies de plusieurs fichiers (ex: T_dissipateur des
essais à 100 W, 200 W et 300 W) en voies logiques.
"""
import re
from dataclasses import dataclass, field

from ressources.custom_types import itemType


def channel_key(name: str) -> str:
    """
    Clé d'appariement d'une voie : nom sans distinction de casse, d'espaces ni de tirets
    bas (« T_dissipateur », « t dissipateur » et « T  Dissipateur » sont la même voie).
    """
    return re.sub(r"[\s_]+", " ", name).strip().casefold()


@dataclass(eq=False)
class ChannelGroup:
    """
    Voie logique : une même voie présente dans plusieurs fichiers.
        key     : clé d'appariement (channel_key)
        name    : nom affiché (celui de la première voie rencontrée)
        signals : une voie par fichier, dans l'ordre des fichiers
    """
    key:        str
    name:       str
    signals:    list = field(default_factory=list)

    item_type = itemType.CHANNEL

    @property
    def display_name(self) -> str:
        return self.name

    @property
    def visible(self) -> bool | None:
        """True / False si toutes les voies sont affichées / masquées, None sinon."""
        states = {sig.visible for sig in self.signals}
        return states.pop() if len(states) == 1 else None


def group_channels(workspace) -> list[ChannelGroup]:
    """Voies logiques du workspace, dans l'ordre de première apparition."""
    groups: dict[str, ChannelGroup] = {}
    for file_obj in workspace.files:
        for sig in file_obj.signals:
            key = channel_key(sig.name)
            if key not in groups:
                groups[key] = ChannelGroup(key=key, name=sig.name)
            groups[key].signals.append(sig)
    return list(groups.values())
