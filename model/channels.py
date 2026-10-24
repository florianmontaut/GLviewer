# model/channels.py
"""
Vue « Par voie » : appariement des voies de plusieurs fichiers (ex: T_dissipateur des
essais à 100 W, 200 W et 300 W) en voies logiques.

Deux modes d'appariement automatique (Workspace.channel_matching) :
    - "name"    : même nom de voie (casse, espaces et tirets bas ignorés)
    - "channel" : même numéro de voie du GL (CH3 avec CH3), ou même colonne pour un
                  fichier .csv / .txt
Les associations faites à la main (Workspace.channel_links) passent avant le mode
automatique ; elles sont propres à chaque mode.
"""
import re
from dataclasses import dataclass, field

from ressources.custom_types import itemType

MATCH_BY_NAME = "name"
MATCH_BY_CHANNEL = "channel"
MATCHING_MODES = (MATCH_BY_NAME, MATCH_BY_CHANNEL)

# réglage « Channel matching between files » (Options > Import settings)
MATCHING_ASK = "Ask when a 2nd file is loaded"
MATCHING_SETTINGS = {
                        MATCHING_ASK                : None,
                        "By channel name"           : MATCH_BY_NAME,
                        "By channel number (CH)"    : MATCH_BY_CHANNEL,
                    }


def channel_key(name: str) -> str:
    """
    Clé d'appariement d'une voie : nom sans distinction de casse, d'espaces ni de tirets
    bas (« T_dissipateur », « t dissipateur » et « T  Dissipateur » sont la même voie).
    """
    return re.sub(r"[\s_]+", " ", name).strip().casefold()


def auto_key(sig, mode: str) -> str:
    """Clé de la voie logique d'un signal en appariement automatique."""
    if mode == MATCH_BY_CHANNEL and sig.channel_id:
        return "ch:" + sig.channel_id.casefold()
    return "name:" + channel_key(sig.name)


def solo_key(sig) -> str:
    """Clé d'une voie mise à part (stable d'une sauvegarde à l'autre)."""
    return f"solo:{sig.file.name}/{sig.name}"


@dataclass(eq=False)
class ChannelGroup:
    """
    Voie logique : une même voie présente dans plusieurs fichiers.
        key     : clé d'appariement (auto_key, solo_key)
        name    : nom affiché
        signals : une voie par fichier, dans l'ordre des fichiers
        manual  : voies associées à la main
    """
    key:        str
    name:       str
    signals:    list = field(default_factory=list)
    manual:     set = field(default_factory=set)

    item_type = itemType.CHANNEL

    @property
    def display_name(self) -> str:
        return self.name

    @property
    def visible(self) -> bool | None:
        """True / False si toutes les voies sont affichées / masquées, None sinon."""
        states = {sig.visible for sig in self.signals}
        return states.pop() if len(states) == 1 else None


def _group_name(sig, mode) -> str:
    if mode == MATCH_BY_CHANNEL and sig.channel_id:
        if channel_key(sig.channel_id) == channel_key(sig.name):
            return sig.channel_id
        return f"{sig.channel_id} · {sig.name}"
    return sig.name


def group_channels(workspace, mode: str | None = None) -> list[ChannelGroup]:
    """
    Voies logiques du workspace, dans l'ordre de première apparition.
        mode : mode d'appariement (par défaut celui du workspace), associations manuelles
               de ce mode comprises
    """
    mode = mode or workspace.matching_mode
    links = workspace.channel_links.get(mode, {})
    signals = [sig for file_obj in workspace.files for sig in file_obj.signals]
    # nom d'une voie logique : celui de sa première voie appariée automatiquement
    names = {}
    for sig in signals:
        if sig not in links:
            names.setdefault(auto_key(sig, mode), _group_name(sig, mode))
    groups: dict[str, ChannelGroup] = {}
    for sig in signals:
        key = links.get(sig) or auto_key(sig, mode)
        if key not in groups:
            name = names.get(key, _group_name(sig, mode))
            # mise à part : étiquette du fichier (point de fonctionnement) si elle est
            # renseignée, sinon nom du fichier
            if key.startswith("solo:"):
                name += f" ({sig.file.label or sig.file.name})"
            groups[key] = ChannelGroup(key=key, name=name)
        groups[key].signals.append(sig)
        if sig in links:
            groups[key].manual.add(sig)
    return list(groups.values())


def same_grouping(workspace) -> bool:
    """True si les deux modes automatiques regroupent les voies de la même façon."""
    def partition(mode):
        return {frozenset(g.signals) for g in group_channels(workspace, mode)}
    return partition(MATCH_BY_NAME) == partition(MATCH_BY_CHANNEL)
