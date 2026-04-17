
# model/pipeline.py

"""
Module utilitaire pour pipeline non destructif.

Ici on peut ajouter :
- invalidation globale
- gestion d'un cache centralisé (si nécessaire)
- DAG de dépendances (signaux dépendants)
"""

def invalidate_signal_and_dependents(signal):
    """
    Invalide le cache d'un signal + potentiellement de tous signal dépendants
    (si on utilise des filtres comme DiffFilter qui utilisent d’autres signaux).
    """
    signal.invalidate()

    # Si le signal a une liste de dependent_signals:
    if hasattr(signal, "dependents"):
        for dep in signal.dependents:
            invalidate_signal_and_dependents(dep)
