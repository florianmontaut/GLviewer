# Documentation du GLviewer passé sur Git


#Initialisation du dépôt
'''bash
git init
git remote add origin SSH_REPO
'''

#Rev01 / Intégration des ThermalModelAnalysis / :
FNT 18/04
    ¤ thermal : réintégration de l'attribut id (uuid) afin de lier les analyses aux derivedSignals
    ¤ action_registry : correction de la méthode ModifyAnalysisCommand (ordre des paramètres)
    ¤ tree_controller : création d'une nouvelle méthode _resolve_signal_node_index afin de simplifier
     la gestion du tri des items
    ¤ graph_controller: ajout de DerivedSignalObject dans le type de paramètre accpeté par add_signal_curve


#Rev02 / Intégration des ThermalModelAnalysis / :
    ¤ TreeItem : ajout de l'attribut item_type afin de simplifier les tests des TreeItems & des Nodes
    ¤ custom_items : modification de la classe ItemType
    ¤ base_analysis/base_object/filter : définition de l'attribut item type
    ¤ diff_external : nouveau analysisNode qui permettra de faire la différence entre deux signaux de file différentes


#Rev03 / Intégration des ThermalModelAnalysis / :
    ¤ MAJ mineure des packages afin de simplifier la création de index_parent (utilisation d'une méthode tree_model qui
    existait déjà mais qui n'était utilisée qu'une seule fois)
    ¤ Mise en gras possible de tout type d'item sélectionable (avant seul les signaux brutes, RAW, pouvaient l'être)
    ¤ Tentative de développer l'item parent lorsque d'un node est créer => échec pour l'instant malgré la modification du
    tree_controller
    ¤ Ajout des paramètres  Puissance d'entrée, Capacité thermique estimée => à implémenter dans les calculs, il faudra
    réfléchir à la bouble input homme vs machine pour la capacité thermique et résistance thermique

=> TODO : il faut ajouter la gestion de la modification des paramètres du modèle et ajouter la vérication
            de la validité du modèle (actuellment l'appli peut cracher si le modèle renvoit des valeurs trop
            importante)