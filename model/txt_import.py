
# model/txt_import.py
"""
Découpage d'un fichier texte (.txt / .csv) de mesures selon les réglages de l'import wizard.
Utilisé à la fois par ImportController.openTxt (chargement) et par l'aperçu du wizard :
l'aperçu montre exactement ce que donnera le chargement.
"""
import csv
from dataclasses import dataclass
from itertools import islice

import numpy as np
import pandas as pd

from ressources.custom_exceptions import TxtDelimiterError, TxtFormatError

# séparateurs essayés quand aucun n'est imposé
DEFAULT_DELIMITERS = ";,\t"
# en dessous de cette part de cellules numériques, le découpage est jugé faux
# (mauvais séparateur de colonnes ou de décimales)
MIN_NUMERIC_RATIO = 0.5


@dataclass
class TxtImport:
    """
    Résultat du découpage.
        data            : DataFrame, colonne 'Time' puis une colonne par voie
        sampling        : pas d'échantillonnage (s)
        invalid_cells   : cellules non numériques remplacées par NaN
    """
    data:           pd.DataFrame
    sampling:       float
    invalid_cells:  int = 0

    @property
    def channels(self) -> list[str]:
        return [c for c in self.data.columns if c != 'Time']


def _delimiter(sample: str, delim: str) -> str:
    """Séparateur imposé (1 caractère) ou détecté parmi les caractères de delim."""
    if len(delim) == 1:
        return delim
    try:
        return csv.Sniffer().sniff(sample, delimiters=delim).delimiter
    except csv.Error as e:
        raise TxtDelimiterError("Séparateur des colonnes indétectable") from e


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


def parse_txt(path, settings: dict, default_sampling: float, max_rows: int | None = None,
              strict: bool = False) -> TxtImport:
    """
    Args:
        settings:   réglages du wizard
                        delim           : séparateur de colonnes (1 caractère) ou caractères
                                          candidats à la détection
                        unitdelim       : séparateur des décimales
                        start           : première ligne de données (après la ligne des
                                          noms), None : aucune ligne
                        columns         : indices des colonnes ignorées
                        sigNames        : la première ligne contient les noms des voies
                        isFirstColIndex : la première colonne conservée est le temps
        default_sampling: pas (s) utilisé quand le temps n'est pas dans le fichier
        max_rows:   nombre maximal de lignes de données lues (aperçu)
        strict:     une colonne sans aucune valeur numérique est une erreur (chargement
                    direct, sans wizard : signe d'un mauvais séparateur des décimales).
                    Sinon elle est chargée vide (réglages vus dans l'aperçu du wizard)
    Raises:
        TxtDelimiterError / TxtFormatError : découpage impossible ou manifestement faux
    """
    start = settings.get('start', 0)
    try:
        # lecture au fil de l'eau : l'aperçu (max_rows) ne lit que le début du fichier
        with open(path, encoding="utf-8-sig", newline="") as f:
            delimiter = _delimiter(f.read(4096), settings.get('delim') or DEFAULT_DELIMITERS)
            f.seek(0)
            reader = (row for row in csv.reader(f, delimiter=delimiter)
                      if any(cell.strip() for cell in row))
            header = next(reader, None) if settings.get('sigNames') else None
            if start is None:
                rows = []
            else:
                rows = list(islice(reader, max(0, start),
                                   None if max_rows is None else max(0, start) + max_rows))
    except UnicodeDecodeError as e:
        raise TxtFormatError("Fichier illisible comme texte (encodage)") from e
    except csv.Error as e:
        raise TxtFormatError(f"Fichier illisible comme texte : {e}") from e

    n_cols = max([len(r) for r in rows] + [len(header) if header else 0], default=0)
    ignored = set(settings.get('columns', []))
    kept = [j for j in range(n_cols) if j not in ignored]
    if not rows or not kept:
        raise TxtFormatError("Aucune donnée : pas de ligne ou de colonne de données "
                             "(sélection vide ou fichier vide)")

    names = []
    for j in kept:
        name = header[j].strip() if header and j < len(header) else ""
        names.append(name or f"channel{j}")
    names = _unique(names)

    decimal = settings.get('unitdelim') or '.'
    # boucle simple : plus rapide que les opérations de chaînes de pandas sur ce volume
    values = np.full((len(rows), len(kept)), np.nan)
    invalid = filled = 0
    for i, row in enumerate(rows):
        for k, j in enumerate(kept):
            cell = row[j].strip() if j < len(row) else ""
            if not cell:
                continue
            filled += 1
            try:
                values[i, k] = float(cell.replace(decimal, '.'))
            except ValueError:
                invalid += 1
    if filled == 0 or (filled - invalid) / filled < MIN_NUMERIC_RATIO:
        raise TxtDelimiterError(
                f"{invalid} cellule(s) sur {filled} ne sont pas des nombres : vérifiez le "
                f"séparateur des colonnes ('{delimiter}') et des décimales ('{decimal}')")
    if strict:
        empty = [name for k, name in enumerate(names) if not np.isfinite(values[:, k]).any()]
        if empty:
            raise TxtDelimiterError(
                f"Aucune valeur numérique dans : {', '.join(empty)} : vérifiez le séparateur "
                f"des décimales ('{decimal}')")

    if settings.get('isFirstColIndex'):
        time = values[:, 0]
        values, names = values[:, 1:], names[1:]
        diffs = np.diff(time[np.isfinite(time)])
        sampling = float(diffs[0]) if diffs.size else default_sampling
    else:
        sampling = default_sampling
        time = np.arange(len(rows)) * sampling

    data = pd.DataFrame(values, columns=names)
    data.insert(0, 'Time', time)
    return TxtImport(data=data, sampling=sampling, invalid_cells=invalid)
