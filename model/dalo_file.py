# model/dalo_file.py
"""
Fichier d'enregistrement d'événement FLXDrive (DALO, voir model.dalo_import) : un
FileObject dont les paramètres affichent les informations de l'événement (lecture seule)
et dont les voies prennent la couleur Matis du fichier ; les voies logiques (0 / 1) sont
marquées is_digital.
"""
import pyqtgraph as pg

from model.base_objects import FileObject
from model.dalo_import import COLORS
from ressources.custom_types import fileType


def _info(label, key):
    return {label: {'type': 'str', 'default': "", "readonly": True, "key": key}}


class DaloFileObject(FileObject):

    # informations de l'événement : clé du ParameterTree -> libellé dans import_params
    EVENT_ATTRIBUTES = {
        "event_name"        : "Event name",
        "event_date"        : "Event date",
        "event_time"        : "Event time",
        "event_occurrences" : "Occurrences",
        "event_file_id"     : "File Id",
        "serial_number"     : "Serial number",
        "app_version"       : "App version",
    }

    PARAMETER_SCHEMA = {
        'File name'     : FileObject.PARAMETER_SCHEMA['File name'],
        'Label'         : FileObject.PARAMETER_SCHEMA['Label'],
        'Event informations': {
                            'type': 'group',
                            'expanded': True,
                            'children': {
                                **_info('Event name', 'event_name'),
                                **_info('Date', 'event_date'),
                                **_info('Time', 'event_time'),
                                **_info('Occurrences', 'event_occurrences'),
                                **_info('File Id', 'event_file_id'),
                                **_info('Serial number', 'serial_number'),
                                **_info('App version', 'app_version'),
                            }
                        },
        'File editor'   : FileObject.PARAMETER_SCHEMA['File editor'],
    }

    def __init__(self, fileData):
        super().__init__(fileData)
        event = self.event
        for attribute, label in self.EVENT_ATTRIBUTES.items():
            setattr(self, attribute, str(event.get(label, "")))

    @property
    def event(self) -> dict:
        return (self.import_params or {}).get("event", {})

    @property
    def tooltip(self) -> str:
        lines = [f"{label} : {value}" for label, value in self.event.items()]
        return "\n".join([self.address, *lines])

    def _channel(self, name) -> dict | None:
        channels = (self.import_params or {}).get("channels", [])
        return next((c for c in channels if c.get("name") == name), None)

    def add_signal(self, name: str):
        """Voie brute : couleur Matis du fichier (voies analogiques), sinon palette."""
        sig = super().add_signal(name)
        settings = self._channel(name) or {}
        color = COLORS.get(settings.get("color") or "")
        if color is not None and not settings.get("digital"):
            sig.pen = pg.mkPen(color=color)
        return sig

    def configure_signal(self, sig):
        """Voie logique et unité (le fichier n'en donne pas : pas de « °C » par défaut)."""
        settings = self._channel(sig.name)
        if settings is None:
            return                              # voie calculée
        sig.is_digital = bool(settings.get("digital"))
        sig.unit = ""


def create_file_object(file_struct) -> FileObject:
    """FileObject adapté au type de fichier importé."""
    if file_struct.file_type == fileType.DALO.name:
        return DaloFileObject(file_struct)
    return FileObject(file_struct)
