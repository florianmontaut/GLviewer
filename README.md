# GLviewer

Visualiseur d'enregistrements de mesures, écrit en Python avec PyQt6 et pyqtgraph. Il est fait d'abord pour les
fichiers des dataloggers Graphtec GL820 / GL840, mais lit aussi des fichiers `.csv` et `.txt` quelconques.

Ce qu'on peut faire :

- superposer plusieurs essais et comparer une même voie d'un fichier à l'autre (vue « Par voie ») ;
- appliquer des filtres **non destructifs** (passe-bas, moyenne glissante, offset, décalage temporel, différence),
  annulables avec Ctrl+Z ;
- lancer des analyses (modèle thermique RC du 1er ordre, FFT, différence entre fichiers) et comparer les modèles
  de plusieurs essais dans la fenêtre Benchmark ;
- créer des voies calculées par formule (`[Débit]/60*4180*([T sortie]-[T entrée])`) ;
- annoter les graphiques, les empiler, les détacher dans leur propre fenêtre ;
- enregistrer le tout dans un projet `.json` qui pointe vers les fichiers de mesure (ils ne sont jamais modifiés).

## Lancer l'application

Environnement validé : Python 3.11, versions dans [requirements.txt](requirements.txt).
Le moteur de formules des voies calculées est un paquet à part,
[formules](https://github.com/florianmontaut/formules), à installer avant `requirements.txt` :

```bash
pip install git+https://github.com/florianmontaut/formules@v0.1.0
```

```bash
../../env/Scripts/python.exe main.py
```

## Lancer les tests

Depuis le dossier GLviewer (environ 550 tests) :

```bash
QT_QPA_PLATFORM=offscreen ../../env/Scripts/python.exe -m pytest -q -W ignore
```

La fixture `ctrl` ([tests/conftest.py](tests/conftest.py)) isole le profil utilisateur : aucun test ne doit
écrire dans le vrai `~/MVC_test/settings.json`.

## Documentation de l'architecture

Les pages sont dans [docs/architecture/](docs/architecture/). Lis-les dans cet ordre :

| Page | Sujet |
|---|---|
| [00 · Vue d'ensemble](docs/architecture/00-vue-ensemble.md) | Dossiers MVC, `MainController` et sous-contrôleurs, carte des signaux Qt |
| [01 · Modèle de données](docs/architecture/01-modele-donnees.md) | `Workspace`, `FileObject`, `SignalObject`, signaux dérivés, `TreeItem` |
| [02 · Pipeline non destructif](docs/architecture/02-pipeline.md) | Signaux bruts, `FilterNode`, cache et recalcul en chaîne |
| [03 · Analyses](docs/architecture/03-analyses.md) | `AnalysisNode`, modèle thermique, FFT, différence externe, Benchmark |
| [04 · Voies calculées](docs/architecture/04-voies-calculees.md) | `ComputedSignal` et le paquet `formules` |
| [05 · Undo / redo](docs/architecture/05-undo-redo.md) | `WorkspaceController`, `ActionRegistry`, commandes, macros |
| [06 · Import](docs/architecture/06-import.md) | Graphtec `.csv`, `.csv` générique, `.txt` et assistant d'import |
| [07 · Projet `.json`](docs/architecture/07-projet-json.md) | Sauvegarde, relecture, compatibilité des anciens projets |
| [08 · Arbres et sélection](docs/architecture/08-arbres-selection.md) | Arbres « Par fichier » et « Par voie », `SelectionContext` |
| [09 · Graphiques et annotations](docs/architecture/09-graphiques-annotations.md) | Panneaux empilés, fenêtres détachées, curseur, textes |
| [10 · Thème](docs/architecture/10-theme.md) | `ressources/theme.py` : clair / sombre, icônes, barre de titre |
| [Guide : ajouter un filtre ou une analyse](docs/architecture/guide-ajouter-un-filtre.md) | Recette pas à pas |

Autres sources :

- [historique_modifs.txt](historique_modifs.txt) : journal des modifications, avec les bugs rencontrés et leurs causes ;
- [docs/archives/](docs/archives/) : anciens diagrammes PlantUML et documents (avril–mai 2026). Ils sont en partie
  dépassés et ne sont gardés que pour mémoire.

## Initialisation du dépôt (rappel)

```bash
git init
git remote add origin SSH_REPO
```
