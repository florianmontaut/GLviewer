# model/benchmark.py
"""
Fenêtre « Benchmark » : résultats des modèles thermiques d'une même voie dans plusieurs
essais (ex: T_dissipateur à 100, 200 et 300 W), en fonction du point de fonctionnement.

Point de fonctionnement : premier nombre de l'étiquette du fichier (« 100 W / 55 °C »
-> 100 W). Rth = ΔT / puissance du modèle thermique (paramètre du modèle, 100 W par
défaut, en attendant les pertes réelles de l'équipement).
"""
import re
from dataclasses import dataclass, field

from ressources.custom_types import qSignalType


@dataclass(frozen=True)
class Quantity:
    label:  str
    unit:   str
    getter: callable      # ThermalFitResult -> float


QUANTITIES = (
    Quantity("ΔT",              "K",    lambda r: r.T_inf - r.T0),
    Quantity("Rth",             "K/W",  lambda r: r.R_th),
    Quantity("T∞ (finale)",     "°C",   lambda r: r.T_inf),
    Quantity("τ",               "s",    lambda r: r.tau),
)

_NUMBER = re.compile(r"([-+]?\d+(?:[.,]\d+)?)\s*([^\s\d/;,()\-+]*)")


def operating_point(label: str) -> tuple[float | None, str]:
    """Premier nombre d'une étiquette et son unité : « 100 W / 55 °C » -> (100.0, "W")."""
    match = _NUMBER.search(label or "")
    if match is None:
        return None, ""
    return float(match.group(1).replace(",", ".")), match.group(2)


def thermal_model(sig):
    """Dernier modèle thermique calculé d'une voie (AnalysisNode), ou None."""
    models = [analysis for analysis in sig.analyses.values()
              if analysis.action_type == qSignalType.MODEL
              and getattr(analysis, "results", None) is not None]
    return models[-1] if models else None


@dataclass
class BenchmarkRow:
    """Un essai (fichier) : nom affiché, point de fonctionnement, modèle par voie."""
    file:   object
    name:   str
    x:      float | None
    unit:   str
    models: dict = field(default_factory=dict)   # ChannelGroup -> AnalysisNode | None


def benchmark_rows(workspace, channels) -> list[BenchmarkRow]:
    """
    Lignes du tableau : un essai par fichier ayant au moins une voie parmi channels,
    triés par point de fonctionnement (ceux sans nombre dans l'étiquette à la fin).
    """
    rows = []
    for file_obj in workspace.files:
        models = {}
        for channel in channels:
            sig = next((s for s in channel.signals if s.file is file_obj), None)
            models[channel] = thermal_model(sig) if sig is not None else None
        if not any(sig.file is file_obj for channel in channels for sig in channel.signals):
            continue
        x, unit = operating_point(file_obj.label)
        rows.append(BenchmarkRow(file_obj, file_obj.label or file_obj.name, x, unit, models))
    order = {row.file: n for n, row in enumerate(rows)}
    rows.sort(key=lambda row: (row.x is None, row.x if row.x is not None else 0,
                               order[row.file]))
    return rows


def value(row: BenchmarkRow, channel, quantity: Quantity) -> float | None:
    model = row.models.get(channel)
    return None if model is None else float(quantity.getter(model.results))


def channels_with_model(channels) -> list:
    """Voies logiques dont au moins une voie a un modèle thermique calculé."""
    return [channel for channel in channels
            if any(thermal_model(sig) is not None for sig in channel.signals)]
