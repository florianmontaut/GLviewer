# model/dalo_import.py
"""
Enregistrement d'événement FLXDrive (« DALO », ex: CHILLER) exporté en .csv :

    en-tête      « clé: valeur » (numéro de série, date et heure de l'événement, nombre
                 d'échantillons avant / après le déclenchement, nombre de voies analogiques
                 et logiques, « Sampling Period in ns », nom de l'événement...)
    voies        Range max value:;...   plage haute de chaque voie
                 Range min value:;...   plage basse
                 Color:;...             couleur (palette Matis, voies analogiques)
                 Time (s);LifeSign;...  noms
    données      temps (s, 0 = déclenchement) puis une colonne par voie, séparateur « ; »

Les voies analogiques viennent d'abord, puis les voies logiques (0 / 1).
"""
import csv
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ressources.custom_exceptions import DaloStructureError

ENCODING = "latin-1"         # en-tête « Rue Amélia EARHART » en ISO-8859-1

# palette Matis (ligne « Color: ») ; WHITE, invisible sur le fond blanc du graphique,
# est tracé en gris foncé
COLORS = {
    'GREY'          : "#747474",
    'YELLOW'        : "#FFFB00",
    'ORANGE'        : "#FF7B00",
    'RED'           : "#FF0000",
    'BLUE'          : "#0026FF",
    'LIGHT_BLUE'    : "#00C3FF",
    'LIGHT_PURPLE'  : "#CA58FF",
    'LIGHT_RED'     : "#F36767",
    'PURPLE'        : "#860092",
    'WHITE'         : "#404040",
    'BROWN'         : "#724400",
    'LIGHT_BROWN'   : "#B16207",
    'GREEN'         : "#2B8801",
    'LIGHT_GREEN'   : "#3ADF24",
    'LIGHT_ORANGE'  : "#F08B49",
}

# lignes de description des voies (début de ligne, sans distinction de casse)
RANGE_MAX, RANGE_MIN, COLOR = "range max value", "range min value", "color"

# informations de l'événement affichées (clé de l'en-tête -> libellé)
EVENT_FIELDS = {
    "Event name"                    : "Event name",
    "Date of event"                 : "Event date",
    "Time of event"                 : "Event time",
    "Event number of occurences"    : "Occurrences",
    "Event nature"                  : "Event nature",
    "Event tag"                     : "Event tag",
    "File Id"                       : "File Id",
    "Equipment serial number"       : "Serial number",
    "Equipment Address"             : "Equipment address",
    "App version"                   : "App version",
    "Data is valid"                 : "Data valid",
}


@dataclass
class DaloImport:
    """
    Résultat de la lecture.
        data        : DataFrame, colonne 'Time' (s, 0 = déclenchement) puis une colonne
                      par voie
        sampling    : période d'échantillonnage (s)
        header      : en-tête complet {clé: valeur}
        channels    : [{'name', 'min', 'max', 'color', 'digital'}] dans l'ordre des voies
        invalid_cells : cellules non numériques (données manquantes)
    """
    data:           pd.DataFrame
    sampling:       float
    header:         dict = field(default_factory=dict)
    channels:       list = field(default_factory=list)
    invalid_cells:  int = 0

    @property
    def event(self) -> dict:
        """Informations de l'événement {libellé: valeur} (champs présents seulement)."""
        return {label: self.header[key] for key, label in EVENT_FIELDS.items()
                if key in self.header}

    @property
    def title(self) -> str:
        """Ex: « F_INV2_OverI_CanThreshold — 02/07/0026 17:59:19 »."""
        when = " ".join(v for v in (self.header.get("Date of event"),
                                    self.header.get("Time of event")) if v)
        name = self.header.get("Event name", "")
        return " — ".join(v for v in (name, when) if v)


def is_dalo(path) -> bool:
    """Le fichier est-il un enregistrement d'événement FLXDrive ? (en-tête seulement)"""
    try:
        with open(path, encoding=ENCODING) as f:
            head = [next(f, "") for _ in range(80)]
    except OSError:
        return False
    return any(line.lower().startswith("sampling period in ns") for line in head) and \
        any(line.lower().startswith(RANGE_MAX) for line in head)


def _number(text: str) -> float:
    try:
        return float(text.strip().replace(",", "."))
    except ValueError:
        return np.nan


def _int(header: dict, key: str) -> int | None:
    try:
        return int(header[key])
    except (KeyError, ValueError):
        return None


def _unique(names: list[str]) -> list[str]:
    seen, out = {}, []
    for name in names:
        if name in seen:
            seen[name] += 1
            name = f"{name} ({seen[name]})"
        else:
            seen[name] = 0
        out.append(name)
    return out


def parse_dalo(path) -> DaloImport:
    """
    Lit un enregistrement d'événement FLXDrive.

    Raises:
        DaloStructureError : description des voies introuvable, aucune donnée...
    """
    with open(path, encoding=ENCODING, newline="") as f:
        rows = list(csv.reader(f, delimiter=";"))

    header, lines = {}, {}
    names_row = None
    for n, row in enumerate(rows):
        first = row[0].strip() if row else ""
        lower = first.lower()
        if lower.startswith(RANGE_MAX):
            lines[RANGE_MAX] = n
        elif lower.startswith(RANGE_MIN):
            lines[RANGE_MIN] = n
        elif lower.startswith(COLOR) and lower.rstrip(":") == COLOR:
            lines[COLOR] = n
        elif RANGE_MAX in lines and first:
            names_row = n                    # 1re ligne non vide après les plages
            break
        elif len(row) == 1 and ":" in first and not first.startswith("*"):
            key, value = first.split(":", 1)
            header[key.strip()] = value.strip()
    if RANGE_MAX not in lines or names_row is None:
        raise DaloStructureError("Ce fichier n'est pas un enregistrement d'événement FLXDrive "
                                 "(lignes « Range max value » / noms des voies introuvables)")

    def cells(row):
        values = [c.strip() for c in row[1:]]
        while values and not values[-1]:
            values.pop()                     # « ; » en fin de ligne
        return values

    names = _unique([name or f"channel{j}" for j, name in
                     enumerate(cells(rows[names_row]), start=1)])
    n_channels = len(names)
    if not n_channels:
        raise DaloStructureError("Aucune voie dans la ligne des noms")

    def per_channel(key, convert):
        values = cells(rows[lines[key]]) if key in lines else []
        values += [""] * (n_channels - len(values))
        return [convert(v) for v in values[:n_channels]]

    highs = per_channel(RANGE_MAX, _number)
    lows = per_channel(RANGE_MIN, _number)
    colors = per_channel(COLOR, lambda v: v.upper() or None)
    n_analog = _int(header, "Number of analog traces")
    channels = []
    for j, name in enumerate(names):
        if n_analog is not None:
            digital = j >= n_analog
        else:                                # pas d'en-tête : voie 0 / 1
            digital = (lows[j], highs[j]) == (0, 1)
        channels.append({"name": name, "min": lows[j], "max": highs[j],
                         "color": colors[j], "digital": digital})

    # données : temps puis une valeur par voie ; cellule non numérique -> manquante
    data_rows = [row for row in rows[names_row + 1:] if any(c.strip() for c in row)]
    if not data_rows:
        raise DaloStructureError("Aucune donnée après la ligne des noms des voies")
    values = np.full((len(data_rows), n_channels + 1), np.nan)
    invalid = 0
    for i, row in enumerate(data_rows):
        for j, cell in enumerate(row[:n_channels + 1]):
            if cell.strip():
                values[i, j] = _number(cell)
                invalid += np.isnan(values[i, j])

    period_ns = _number(header.get("Sampling Period in ns", ""))
    time = values[:, 0]
    if np.isfinite(period_ns) and period_ns > 0:
        sampling = period_ns * 1e-9
    else:
        steps = np.diff(time[np.isfinite(time)])
        sampling = float(np.median(steps)) if steps.size else 1.0
    if not np.isfinite(time).all():
        # colonne temps incomplète : reconstruite, déclenchement à 0
        pre = _int(header, "Number of pre-trigger samples") or 0
        time = (np.arange(len(data_rows)) - pre) * sampling

    data = pd.DataFrame(values[:, 1:], columns=names)
    data.insert(0, "Time", time)
    return DaloImport(data=data, sampling=sampling, header=header, channels=channels,
                      invalid_cells=int(invalid))
