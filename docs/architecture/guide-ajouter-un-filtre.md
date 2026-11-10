# Guide : ajouter un filtre ou une analyse

Cette recette s'appuie sur [02 · Pipeline](02-pipeline.md), [03 · Analyses](03-analyses.md) et
[05 · Undo / redo](05-undo-redo.md). Exemple suivi : un filtre « Gain » qui multiplie la voie par un facteur.

## 1. Le type d'action

Ajoute un membre à `qSignalType` ([ressources/custom_types.py](../../ressources/custom_types.py)) :

```python
GAIN        = auto()
```

Son **nom** (`"GAIN"`) est écrit dans les projets `.json` : ne le renomme plus une fois des projets enregistrés.

## 2. La classe du node

Crée `model/filters/gain.py` sur le modèle d'[offset.py](../../model/filters/offset.py) :

```python
from .base_filter import FilterNode
from ressources.custom_types import qSignalType

class GainFilter(FilterNode):
    action_type = qSignalType.GAIN
    PARAMETER_SCHEMA = {
        "Gain": {"type": "float", "default": 1.0, "readonly": False, "key": "gain"},
    }

    def validate(self, params):
        if not isinstance(params["gain"], (int, float)):
            raise ValueError("Gain must be numeric")

    @property
    def display_name(self) -> str:
        return f'Gain(×{self.get_param("gain"):g})'

    def apply(self, x, y):
        return y * self.get_param("gain")      # nouveau tableau : y n'est pas modifié
```

Règles à respecter :

- **`apply` / `apply_x` renvoient de nouveaux tableaux** : l'axe des temps est partagé par toutes les voies du
  fichier et il est en lecture seule.
- **Les NaN sont des données manquantes** : un filtre qui les propagerait à tout le signal (`filtfilt`, convolution)
  doit utiliser `fill_gaps` ([model/missing_data.py](../../model/missing_data.py)), comme `LowPassFilter`.
- **Ne garde pas d'état mutable** : le node est immuable, et une modification passe par `clone_with`.
- Si le filtre dépend d'une autre voie, sauvegarde-la **par son nom** dans `get_params()` et résous-la à la
  relecture (voir `DiffFilter.resolve_reference`).

Pour **une analyse**, hérite d'`AnalysisNode` ([base_analysis.py](../../model/analysis/base_analysis.py)) et écris
`compute(parent_signal)`, qui renvoie un `DerivedSignalObject` (exemple court : [fft.py](../../model/analysis/fft.py)).
Si l'analyse dépend d'autre chose que son signal parent, surcharge `input_key`. Lève une `AnalysisError` ou une
`ValueError` en cas de calcul impossible : le `WorkspaceController` affiche le message, et rien n'est empilé.

## 3. La factory

Inscris la classe dans `REGISTRY` :

- filtre : [`FilterFactory`](../../model/filters/filter_factory.py) ;
- analyse : [`AnalysisFactory`](../../model/analysis/analysis_factory.py).

La relecture des projets passe par ces registres.

## 4. Les commandes undo/redo

Dans [`ActionRegistry._init_action_dict`](../../controller/commands/action_registery.py), ajoute le type au tuple
des filtres, ou à celui des analyses. Les trois commandes Add, Modify et Remove sont alors créées
automatiquement. Il n'y a pas de nouvelle commande à écrire.

## 5. Le menu

- Libellé et condition d'activation : `ACTION_SPECS` de `BaseContextMenu`
  ([ressources/custom_menu.py](../../ressources/custom_menu.py)).
- Ajout dans les menus contextuels : `_build_menu` de
  [tree_context_menu_controller.py](../../controller/tree_context_menu_controller.py) et de
  [graph_context_menu_controller.py](../../controller/graph_context_menu_controller.py).
- Pour l'action groupée de la vue « Par voie » : `GROUP_ACTIONS` dans
  [channel_tree_controller.py](../../controller/channel_tree_controller.py).

Le reste du chemin est générique : le menu émet `menu_actions_triggered`, `MainController._action_concentrator`
appelle `_build_action_request`, qui appelle `WorkspaceController.push`. Par défaut, le node est créé avec les
valeurs par défaut de son schéma, et l'utilisateur les règle ensuite dans le ParameterTree. Si des paramètres
doivent être calculés à la création (comme `fs` pour le passe-bas), ajoute un cas dans
`MainController._ask_filter_params` et dans la condition de `_build_action_request`.

Remarque : `MovingAverageFilter` (`AVG`) est enregistré dans les factories et l'`ActionRegistry`, mais il n'a pas
d'entrée de menu pour l'instant.

## 6. Les tests

À ajouter dans [tests/](../../tests/) (la fixture `ctrl` donne un `MainController` complet, avec un profil isolé) :

- calcul : `apply` sur un petit tableau, données manquantes comprises ;
- undo/redo : ajout, modification par le ParameterTree, Ctrl+Z, Ctrl+Y (exemples dans
  [test_pipeline.py](../../tests/test_pipeline.py) et [test_chained_actions.py](../../tests/test_chained_actions.py)) ;
- sauvegarde : enregistrer puis rouvrir un projet qui contient le node
  ([test_project_io.py](../../tests/test_project_io.py)) ;
- analyse : recalcul quand l'entrée change ([test_analysis_refresh.py](../../tests/test_analysis_refresh.py)).

```bash
QT_QPA_PLATFORM=offscreen ../../env/Scripts/python.exe -m pytest -q -W ignore
```
