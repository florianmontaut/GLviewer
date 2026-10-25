# model/missing_data.py
"""
Données manquantes : les échantillons absents ou invalides (BURNOUT d'un GL, cellule vide
d'un .txt, voie calculée hors de la zone commune...) valent NaN dans les données.
Les calculs les excluent ; l'affichage les montre par une interruption de la courbe ou
par une valeur de remplacement (option du graphique, voir GraphController).
"""
import numpy as np


def fill_gaps(x, y) -> tuple[np.ndarray, np.ndarray]:
    """
    Comble les trous par interpolation linéaire, le temps d'un calcul qui ne supporte
    pas les NaN (filtre passe-bas, FFT). Avant le premier / après le dernier point
    valide : valeur valide la plus proche.

    Args:
        x : axe des temps (None : échantillons régulièrement espacés)
        y : valeurs

    Returns:
        (valeurs comblées, masque des échantillons manquants). Sans aucun point
        valide, les valeurs sont rendues telles quelles.
    """
    y = np.asarray(y, dtype=float)
    missing = ~np.isfinite(y)
    if not missing.any() or missing.all():
        return y, missing
    x = np.arange(len(y), dtype=float) if x is None else np.asarray(x, dtype=float)
    filled = y.copy()
    filled[missing] = np.interp(x[missing], x[~missing], y[~missing])
    return filled, missing


def valid_on(t_src, y_src, t_target) -> np.ndarray:
    """
    Instants de t_target qui ne tombent pas dans un trou de (t_src, y_src) : un
    instant entre un échantillon valide et un échantillon manquant est manquant.
    """
    valid = np.isfinite(np.asarray(y_src, dtype=float)).astype(float)
    return np.interp(t_target, t_src, valid) > 1 - 1e-9


def display_values(y, placeholder: float | None) -> np.ndarray:
    """Valeurs affichées : NaN (interruption de la courbe) ou valeur de remplacement."""
    if placeholder is None:
        return y
    y = np.asarray(y, dtype=float)
    missing = ~np.isfinite(y)
    if not missing.any():
        return y
    return np.where(missing, placeholder, y)
