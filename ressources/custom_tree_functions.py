from PyQt6 import QtCore
from PyQt6.QtWidgets import QTreeWidget,QTreeWidgetItem,QTreeWidgetItemIterator

from .custom_types import itemType


def search(tree:QTreeWidget,term:str)->list[QTreeWidget]:
    """
    Sélectionne les items dont le nom contient les lettres, mots recherchés.
    Arguments:
            tree {QTreeWidget}  -- Arborescence devant être examinée
            term {str}          -- Mots ou lettres recherchés
    Returns:
            None                -- Sélection des items repondant à la recherche
    """
    if isinstance(term,str):
        text=term.strip()
        if not text:
            #si text vide => on quitte la Fontion search
            return
    else:
        return
    output=[]
    matchlist = tree.findItems(text,QtCore.Qt.MatchFlag.MatchContains |
                                QtCore.Qt.MatchFlag.MatchRecursive, 0)
    if matchlist:
        for item in matchlist:
            if not item.flags()& QtCore.Qt.ItemFlag.ItemIsAutoTristate:
                item.setSelected(True)
                output.append(item)
    return output

def getItems(tree:QTreeWidget,item:QTreeWidgetItem=None,
            type_methode:str='selected') -> list[QTreeWidgetItem]:
    """
    Retourne une liste de listes d'indices des différents signaux répondant aux paramètres
    recherchés. Fontion à privilégier pour le traitement des données.
    Arguments:
        tree {QTreeWidget} --  Arborescence (TreeWidget) devant être examiner
        type_methode {str} --  Configuration des paramètres de recherche: 'selected' recherche
                                des éléments sélectionnés ; 'checked' recherches des élements
                                cochés sans enfant
    Return:
        it_list {list{QTreeWidgetItems} -- Liste des items répondant à la recherche
    """
    #utilisation d'un dictionnaire afin de simplifier l'appel de la Fontion
    dict_methode={'selected':QTreeWidgetItemIterator.IteratorFlag.Selected|
                    QTreeWidgetItemIterator.IteratorFlag.Enabled|
                    QTreeWidgetItemIterator.IteratorFlag.NoChildren,
                'checked':QTreeWidgetItemIterator.IteratorFlag.Checked|
                        QTreeWidgetItemIterator.IteratorFlag.Enabled|
                        QTreeWidgetItemIterator.IteratorFlag.NoChildren,
                "children":QTreeWidgetItemIterator.IteratorFlag.Enabled|
                        QTreeWidgetItemIterator.IteratorFlag.NoChildren}
    it_list=[]
    if item is None:
        it_tree=QTreeWidgetItemIterator(tree,flags=dict_methode[type_methode])
    else:
        it_tree=QTreeWidgetItemIterator(item,flags=dict_methode[type_methode])

    while it_tree.value():
        current_item=it_tree.value()
        #on ne passe que les items qui ne sont pas tristate (True,False,PartialTrue)
        if current_item.type is not itemType.FILE:
            it_list.append(current_item)
        it_tree+=1

    return it_list

def isolateItems(tree,q_items:list):
    """
    Méthode permettant de cocher uniquement le(s) élément(s) sélectionné(s)
    Arguments:
            tree   {QTreeWidget}           --   Arborescence (TreeWidget) devant être examiner
            QItems {list[QTreeWidgetItem]} --   Si None la fonction récupère la
                                                sélection actuelle dans le treefile
    Returns:
            None   --
    """

    try:
        it_tree=QTreeWidgetItemIterator(tree)
        table_item=[]
        while it_tree.value():
            table_item.append(it_tree.value())
            it_tree+=1
        for item in table_item:
            if item in q_items:
                item.setCheckState(0, QtCore.Qt.CheckState.Checked)
            else:
                item.setCheckState(0, QtCore.Qt.CheckState.Unchecked)
    except:
        pass


class CustomTreeWidget(QTreeWidget):

    FilterItem=QtCore.pyqtSignal(list)
    ModelItem=QtCore.pyqtSignal(list)
    PaintItem=QtCore.pyqtSignal(list)

    def __init__(self,*arg,**kwargs):
        super(CustomTreeWidget,self).__init__(*arg,**kwargs)

    def filterEvent(self,item):

        self.FilterItem.emit([item])

    def ModelEvent(self,item):

        self.ModelItem.emit([item])

    def PaintEvent(self,item):

        self.selectionModel().clear()
        item.setSelected(True)
        self.PaintItem.emit([item])

    def SelectedEvent(self,item):


        self.selectionModel().clear()
        item.setSelected(True)
        self.itemClicked.emit(item,0)
