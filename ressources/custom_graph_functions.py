from PyQt6 import QtCore,QtGui
from PyQt6.QtWidgets import QTreeWidgetItem

import pyqtgraph as pg

#!METTRE A JOUR
def setItemFont(tree_item:QTreeWidgetItem,bold:bool=None,brush:pg.mkBrush=None):
    """
    Fontion permettant de modifier les données graphiques d'un TreeWidgetItem.\n
    Arguments:
            line_item  {PlotDataItem}    -- Courbe à modifier
    Returns:
            pen     {pg.mkPen}           -- Objet pyqtgraph.mkPen définissant l'aspect de la courbe
    """
    if bold is not None:
        font=QtGui.QFont()
        font.setBold(bold)
        tree_item.setData(0,6,font)
    if brush is not None:
        tree_item.setData(0,8,brush)
        tree_item.setData(1,8,brush)

def updateCurve(curve:pg.PlotDataItem,width:int=None,
                z_val:int=None,color:QtCore.Qt.GlobalColor=None):
    """
    Fontion permettant de modifier les données graphiques d'un PlotDataItem
    Arguments:
            curve      {PlotDataItem}       --  Courbe à modifier
            width       {int}               --  Nouvelle épaisseur du tracé courbe
            z_val        {int}              --  Position en Z de la courbe (plus Z est élevé
                                                plus la courbe est mise en avant)
            color       {Qt.GlobalColor}    --  Nouvelle couleur de la courbe
    Returns:
            pen     {pg.mkPen}              --  Objet pyqtgraph.mkPen définissant
                                                l'aspect de la courbe
    """
    pen = curve.opts['pen']
    defaultpenWidth=int(curve.opts['pen'].width() /2)
    #print(defaultpenWidth)
    if width is None :
        if defaultpenWidth<=1:
            defaultpenWidth=1
        pen.setWidth(defaultpenWidth)
    else:
        pen.setWidth(width)
    if z_val is None :
        curve.setZValue(0)
    else:
        curve.setZValue(z_val)
    if color:
        pen.setColor(color)
    curve.setPen(pen)
