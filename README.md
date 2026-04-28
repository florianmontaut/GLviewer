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


#Rev04 / Intégration des ThermalModelAnalysis / :
    ¤ MAJ majeure des packages afin de simplifier la synchronisation de la selection via l'utilisation d'une dataclasse unique
    SelectionContext
    ¤ Correction et protection contre un bug provoquant le crash de l'application à cause de la mise à jour du graphique lors
    du undo/redo. Maintenant le workspace hérite de graph_controller et peut stopper la MAJ du graph afin d'éviter toute erreur
    du type QPaintDevice: Cannot destroy paint device that is being painted

#Rev05 / Révision de l'import de fichier .csv du graphtec / :
    ¤ MAJ majeure de la méthode openGLCsvFiles afin de pouvoir charger tout les types de fichiers venant des graphtecs et ce
    peut importe la version du firmwire, software ou type de graphtec utilisé : testé avec des enregirstrement de 2015 à 2026
    venant de GL820, 840.

#Rev06 / Révision du SelectionContext / :
FNT 28/04
    ¤ Modification de la méthode select_tree_from_context du TreeController afin de sélectionner le node, et non plus le signal
    lorsque l'utilisateur ajoute un filtre ou une analyse.
    ¤ Dans cette même méthode blockage du signal itemselected afin d'éviter un bouble appel de la méthode select_from_context
    du main_controller (quand l'utilisateur cliquait sur une courbe, le graph_controller, puis le tree_controller étaient appelés)


