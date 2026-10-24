# controller/commands/channel_link.py
from PyQt6.QtGui import QUndoCommand


class ChannelLinkCommand(QUndoCommand):
    """
    Vue « Par voie » : associe à la main une voie d'un fichier à une voie logique
    (key), ou lui rend son appariement automatique (key None). L'association ne vaut
    que pour le mode d'appariement en vigueur (par nom / par numéro CH).
    """

    def __init__(self, controller, sig, key: str | None):
        super().__init__(f"Channel matching {sig.name}")
        self.controller = controller
        self.sig = sig
        self.key = key
        workspace = controller.workspace
        self.links = workspace.channel_links.setdefault(workspace.matching_mode, {})
        self.old_key = self.links.get(sig)

    def _apply(self, key):
        if key is None:
            self.links.pop(self.sig, None)
        else:
            self.links[self.sig] = key
        self.controller.channel_model.rebuild()

    def redo(self):
        self._apply(self.key)

    def undo(self):
        self._apply(self.old_key)


class ChannelMatchingCommand(QUndoCommand):
    """Change le mode d'appariement des voies du workspace (par nom / par numéro CH)."""

    def __init__(self, controller, mode: str):
        super().__init__(f"Channel matching by {mode}")
        self.controller = controller
        self.mode = mode
        self.old_mode = controller.workspace.channel_matching

    def _apply(self, mode):
        self.controller.workspace.channel_matching = mode
        self.controller.channel_model.rebuild()

    def redo(self):
        self._apply(self.mode)

    def undo(self):
        self._apply(self.old_mode)


class ChannelGroupsCommand(QUndoCommand):
    """
    Groupes de voies de la vue « Par voie » (création, renommage, ajout / retrait de
    voies, suppression) : l'état complet des groupes avant / après est conservé.
        groups : nouvel état, liste de (id, nom, clés des voies)
    """

    def __init__(self, controller, groups: list, text: str):
        super().__init__(text)
        self.controller = controller
        self.new_state = [(gid, name, list(keys)) for gid, name, keys in groups]
        self.old_state = self.snapshot(controller.workspace)

    @staticmethod
    def snapshot(workspace) -> list:
        return [(g.id, g.name, list(g.keys)) for g in workspace.channel_groups]

    def _apply(self, state):
        from model.channels import UserGroup
        workspace = self.controller.workspace
        existing = {g.id: g for g in workspace.channel_groups}
        groups = []
        for gid, name, keys in state:
            # même objet si le groupe existait : son dépliage est conservé
            group = existing.get(gid) or UserGroup(name=name, id=gid)
            group.name, group.keys = name, list(keys)
            groups.append(group)
        workspace.channel_groups = groups
        self.controller.channel_model.rebuild()

    def redo(self):
        self._apply(self.new_state)

    def undo(self):
        self._apply(self.old_state)
