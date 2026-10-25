# model/formula/errors.py
from ressources.custom_exceptions import AnalysisError


class FormulaError(AnalysisError, ValueError):
    """Formule invalide (syntaxe, voie inconnue, erreur de calcul)."""
