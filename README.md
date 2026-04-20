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

=> TODO : il faut ajouter la gestion de la modification des paramètres du modèle et ajouter la vérication 
            de la validité du modèle (actuellment l'appli peut cracher si le modèle renvoit des valeurs trop
            importante)