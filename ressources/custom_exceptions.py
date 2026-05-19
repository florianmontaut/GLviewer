

class MissingParameters(Exception):
    """Erreur de paramètres manquants pour la création d'une analyse
    (analysisNode)

    Args:
        Exception (_type_): _description_
    """
    def __init__(self, missing, params=None):
        self.missing = missing
        self.params = params or {}
        super().__init__(f"Missing parameters: {missing}")




class TxtImportError(Exception):
    """Erreur générique d'import TXT"""
    pass

class CsvImportError(Exception):
    """Erreur générique d'import CSV"""
    pass

class GLImportError(Exception):
    """Erreur générique d'import GL"""
    pass

class JSONImportError(Exception):
    """Erreur générique d'import JSON"""
    pass


class TxtDelimiterError(TxtImportError):
    """Délimiteur incorrect ou indétectable"""
    pass

class TxtFormatError(TxtImportError):
    """Erreur de conversion ou de structure des données"""
    pass


class CsvStructureError(CsvImportError):
    """Colonnes incohérentes / lignes invalides"""
    pass


class GLStructureError(GLImportError):
    """Colonnes incohérentes / lignes invalides"""
    pass

class JSONStructureError(JSONImportError):
    """Colonnes incohérentes / lignes invalides"""
    pass

class AnalysisError(Exception):
    """Erreur générique d'analyse."""
    pass


class InvalidModelFit(AnalysisError):
    """Le modèle est mathématiquement ou physiquement invalide."""
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason
