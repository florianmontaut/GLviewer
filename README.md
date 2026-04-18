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

=> TODO : la création d'un AnalysisNode ne met pas à jour le graph widget (add_signal_curve) par conséquent
        aucune modèle n'apparait sur le graphique. Il faut donc soit simplement ajouter cette mise à jour
        ou gérer la création des modèles différements. L'idée la plus souple serait de passer par la
        création systématique d'un DialogBox demander les bornes avant après la création de l'analysis node
        en vue de la création du derivedSignal.