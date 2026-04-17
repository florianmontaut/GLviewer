"""
Module dédié aux paramètres complexes personnalisés pouvant servir pour différents projets:
    ¤La classe curveModelizer gère l'affichage de l'utilitaire de modélisation
    ¤La classe curveModelItem gère l'affichage et les stockages des paramètres d'un model
    ¤La classe complementaryElements gère la création de deux champs de float complémentaire
    ¤La classe linkedCursors gère intégralement une paire de curseur pouvant être chargé dans un
    PlotWidget

"""
import numpy as np
from PyQt6 import QtGui,QtWidgets,QtCore


import pyqtgraph as pg
import pyqtgraph.parametertree.parameterTypes as pTypes

import ressources.modelFunctions as mf
from .custom_types import modelType


import pyqtgraph.parametertree.parameterTypes as pTypes
from PyQt6.QtWidgets import QApplication


class ThermalModelizerParameter(pTypes.GroupParameter):
    """
    UI pour lancer une analyse thermique RC
    """

    def __init__(self, analysis, cursor_provider=None, **opts):
        """
        analysis : instance de ThermalModelAnalysis
        cursor_provider : callable returning (t_start, t_end)
        """
        super().__init__(**opts)
        self.analysis = analysis
        self.cursor_provider = cursor_provider

        params = [
            {"name": "Create model", "type": "action"},
            {"name": "Use vertical cursors as limits", "type": "bool", "value": True},
            {"name": "Projection duration (s)", "type": "float", "value": 0.0},
            {"name": "Show modeling curve", "type": "bool", "value": True},
        ]

        self.addChildren(params)
        self.param("Create model").sigActivated.connect(self._run_model)

    def _run_model(self):
        if self.param("Use vertical cursors as limits").value() and self.cursor_provider:
            t_start, t_end = self.cursor_provider()
            self.analysis.set_fit_range(t_start, t_end)

        # Ici, x, y et power sont fournis par le contrôleur
        self.sigTreeStateChanged.emit(
                                        {"action": "run_model"}
                                    )

class ThermalModelResultParameter(pTypes.GroupParameter):
    """
    UI de consultation / mise à jour du modèle thermique
    """

    def __init__(self, analysis, **opts):
        super().__init__(**opts)
        self.analysis = analysis

        params = [
                {"name": "τ (s)", "type": "float", "value": 0.0, "readonly": True},
                {"name": "R_th (K/W)", "type": "float", "value": 0.0, "readonly": True},
                {"name": "C_th (J/K)", "type": "float", "value": 0.0, "readonly": True},
                {"name": "RMSE", "type": "float", "value": 0.0, "readonly": True},
                {"name": "Copy parameters", "type": "action"},
                {"name": "Update model", "type": "action", "enabled": False},
            ]

        self.addChildren(params)
        self.param("Copy parameters").sigActivated.connect(self._copy)
        self.param("Update model").sigActivated.connect(self._update)

    def update_from_analysis(self):
        r = self.analysis.results
        if r is None:
            return

        self.param("τ (s)").setValue(r.tau)
        self.param("R_th (K/W)").setValue(r.R_th)
        self.param("C_th (J/K)").setValue(r.C_th)
        self.param("RMSE").setValue(r.rmse)

    def _copy(self):
        if self.analysis.results:
            text = (
                f"tau={self.analysis.results.tau}\n"
                f"Rth={self.analysis.results.R_th}\n"
                f"Cth={self.analysis.results.C_th}"
            )
            QApplication.clipboard().setText(text)

    def _update(self):
        self.sigTreeStateChanged.emit(
                                        {"action": "update_model"}
                                    )


class ComplementaryElements(pTypes.GroupParameter):
    """
    Classe héritant de pyqtgraph.parametertree.parameterTypes. Permet de rapidement créer
    des paramètres complémentaires du type A+B=cste.
    """

    def __init__(self,start=0,stop=10000, **opts):

        pTypes.GroupParameter.__init__(self, **opts)
        default_start=opts.get('df_start',start)
        default_stop=opts.get('df_stop',stop)

        self.addChild({ 'name': 'start',
                        'type': 'int',
                        'limits':[0, stop-1],
                        'value': start,
                        'default':default_start})
        self.addChild({ 'name': 'stop',
                        'type': 'int',
                        'limits':[1, default_stop],
                        'value': stop,
                        'default':default_stop})

        self.a = self.param('start')
        self.b = self.param('stop')
        self.a.sigValueChanged.connect(self.aChanged)
        self.b.sigValueChanged.connect(self.bChanged)

    def aChanged(self):
        """
        Méthode gérant la mise à jour du champ "start"
        """
        if self.a.value() >=self.b.value():
            self.a.setValue(self.b.value()-1, blockSignal=self.aChanged)
    def bChanged(self):
        """
        Méthode gérant la mise à jour du champ "stop"
        """
        if self.b.value()<=self.a.value():
            self.b.setValue(self.a.value()+1, blockSignal=self.bChanged)



class LinkedCursors(pTypes.GroupParameter):
    """
    Classe héritant de pyqtgraph.parametertree.parameterTypes. Permet de rapidement créer
    des curseurs graphiques dont la valeur est renvoyée dans un parameterTreeItem
    """
    def __init__(self,graphWidget, **opts):

        opts['expanded']=False
        self.linkedojects=[]
        self.cursors=[]
        self.arrows=[]
        self.oldState=[0,0]
        self.graph=graphWidget
        self.sig_cursor_1=None
        self.sig_cursor_2=None

        for i,value in enumerate(opts['cursors_setting']['pos']):
            self.cursors.append(pg.InfiniteLine(angle=opts['cursors_setting']['angle'],
                                    movable=True,
                                    pos=value,
                                    pen=opts['cursors_setting']['pen'],
                                    label=opts['cursors_setting']['label'],
                                    labelOpts=opts['cursors_setting']['labelOpts']))
            if opts['cursors_setting']['angle']==90:
                angle=0+180*i
            else:
                angle=90+180*i
            self.arrows.append(pg.ArrowItem(angle=angle,
                                            tipAngle=30,
                                            baseAngle=00,
                                            headLen=10,
                                            tailLen=50,
                                            pos=(value,50)))

        #passages des options à la classe parent GroupParameter
        pTypes.GroupParameter.__init__(self, **opts)

        #création des paramètres :
        if opts['name']=="Vertical cursors":
            values=[self.cursors[0].pos().x(),self.cursors[1].pos().x()]
        else:
            values=[self.cursors[0].pos().y(),self.cursors[1].pos().y()]

        params=[
                    {'name':'show cursors', 'type': 'bool','value':False},
                    {'name':'show delta on graph','type':'bool','value':False},
                    {'name':'cursor 1', 'type': 'float','value':values[0]},
                    {'name':'cursor 2', 'type': 'float','value':values[1]},
                    {'name':'delta','type': 'float','value':values[1]-values[0],'readonly': True}
                ]
        self.addChildren(params)

        #création des paramètres :
        self.newLinkedObjects(field=self.param('cursor 1'),item=self.cursors[0])
        self.newLinkedObjects(field=self.param('cursor 2'),item=self.cursors[1])
        self.sigTreeStateChanged.connect(self.updateGraph)

    @property
    def display_name(self) -> str:
        #voir méthode ci-dessus, ne pas remplacer par  get_param !!
        return f"Diff ({self.get_params()['reference']})"


    def cursorsState(self,state):
        """
        Méthode permettant d'ajouter ou retirer les curseurs
        Args:
            state {bool} -- état logique du paramètre "Show Cursors"
        """
        if state:
            #on recharge les droites représentant le curseur
            self.graph.addItem(self.cursors[0], ignoreBounds=True)
            self.graph.addItem(self.cursors[1], ignoreBounds=True)
        else:
            #on recharge les droites représentant le curseur
            self.graph.removeItem(self.cursors[0])
            self.graph.removeItem(self.cursors[1])

    def arrowsState(self,state):
        """
        Méthode permettant d'ajouter ou retirer les flèches
        Args:
            state {bool} -- état logique du paramètre "Show delta"
        """
        if state:
            #on recharge les droites représentant le curseur
            self.graph.addItem(self.arrows[0], ignoreBounds=True)
            self.graph.addItem(self.arrows[1], ignoreBounds=True)
        else:
            #on recharge les droites représentant le curseur
            self.graph.removeItem(self.arrows[0])
            self.graph.removeItem(self.arrows[1])


    def updateGraph(self,changes):
        """Méthode permettant d'afficher ou non les curseurs en fonction de l'état
        logique du parameterTreeItem associé

        Args:
            field (parameterItem): paramaterItem lié à l'une des coordonnées de l'objet graphique
            item (GraphicsObject): objet graphique lié
        """
        if changes['show cursors']!=self.oldState[0]:
            self.oldState[0]=changes['show cursors']
            self.cursorsState(self.param('show cursors').value())
        elif changes['show delta on graph']!=self.oldState[1]:
            self.arrowsState(self.param('show delta on graph').value())


    def updateDelta(self):
        """
        Méthode permettant de calculer le delta entre deux curseurs
        Args:
            field (parameterItem): paramaterItem lié à l'une des coordonnées de l'objet graphique
            item (GraphicsObject): objet graphique lié
        """

        self.param('delta').setValue(self.param('cursor 2').value()-self.param('cursor 1').value())
        #todo : test si delta vertical/horizontal
        if self.param('show delta on graph').value():
            self.arrows[0].setPos(self.param('cursor 1').value(),50)
            self.arrows[1].setPos(self.param('cursor 2').value(),50)

    def newLinkedObjects(self,field,item,**opts):
        """
        Méthode permettant de relier la position d'un item graphique à un paramaterItem
        de type float
        Args:
            field (parameterItem): paramaterItem lié à l'une des coordonnées de l'objet graphique
            item (GraphicsObject): objet graphique lié
        """

        index=len(self.linkedojects)

        def field_Changed(field,item):
            """
            Méthode interne permettant de relier le changement de la valeur du champ/parameterItem
            à la position (x ou y) de l'objet graphique
            Args:
                f (parameterItem): paramaterItem lié à l'une des coordonnées de l'objet graphique
                it (GraphicsObject): objet graphique lié
            """
            if field.value() !=item.pos():
                item.setPos(field.value())
                self.updateDelta()

        #lambda est nécessaire pour affecter une fonction à l'élément [id][0] de linkedojects.
        #Si field_Changed(field,item) était directement passé, un message d'erreur NoneType
        #apparaitrait
        self.linkedojects.append([lambda :field_Changed(field,item),None])

        def item_Changed(field,item,index:int):
            """
            Méthode interne permettant de relier le changement de position de l'objet graphique
            à la mise à jour du champ/parameterItem
            Args:
                field {parameterItem}   --  paramaterItem lié à l'une des coordonnées
                                            de l'objet graphique
                item {GraphicsObject}   --  objet graphique lié
                index {int}             --  index de la méthode chargée dans linkedobjects
                                            (field_Changed(f,it)) devant être bloquée afin
                                            d'éviter une boucle infinie
            """
            if item.pos() !=field.value():
                if self.opts['name']=="Vertical cursors":
                    val=item.pos().x()
                else:
                    val=item.pos().y()
                field.setValue(val, blockSignal=self.linkedojects[index][0])
                self.updateDelta()

        self.linkedojects[index][1]=lambda :item_Changed(field,item,index)
        field.sigValueChanged.connect(self.linkedojects[index][0])
        item.sigPositionChanged.connect(self.linkedojects[index][1])


    def getParams(self):
        """
        Méthode retourant toute les données des deux curseurs: positions 1 & 2 ainsi que le delta
        Returns:
            Lits({float},{float},{float})  --  différence entre les deux curseurs
        """

        return {'cursor_1'      : self.param('cursor 1').value(),
                'cursor_2'      : self.param('cursor 2').value(),
                'delta'         : self.param("delta").value(),
                'cursor_1_ref'  : self.sig_cursor_1,
                'cursor_2_ref'  : self.sig_cursor_2}

class MouseCursors(pTypes.GroupParameter):
    """
    Classe héritant de pyqtgraph.parametertree.parameterTypes. Permet de rapidement créer
    un curseur de souris dont les valeurs sont renvoyées dans un parameterTreeItem
    """
    def __init__(self,graphWidget,curve=None, **opts):

        opts['expanded']=False
        self.linkedojects=[]
        self.cursors=[]
        self.valtext=pg.TextItem("", anchor=(1.5, -0.5),color=(100,100,100))
        font=QtGui.QFont()
        font.setBold(True)
        self.valtext.setFont(font)
        self.valtext.setZValue(20)
        self.textIndex=-1
        self.graph=graphWidget
        self.curve=curve
        self.curvePoint=None

        #self.lastPos=None
        #modif du 05/10, mouseCursors utilisera la méthode MouseUpdate de View
        #afin de limiter le nombre de proxy.
        #self.vb = self.graph.vb


        for i in range(2):
            value=90*(1-i)
            self.cursors.append(pg.InfiniteLine(angle=value,
                                    movable=False,
                                    pos=value,
                                    pen=(100,100,100)))
        #passages des options à la classe parent GroupParameter
        pTypes.GroupParameter.__init__(self, **opts)

        params=[
                    {'name':'show cursors', 'type': 'bool','value':False},
                    {'name':'snap to selected signal','type':'bool','value':False,'enabled':False},
                    {'name':'show X value','type':'bool','value':False,'enabled':False},
                    {'name':'show Y value','type':'bool','value':False,'enabled':False}
                ]
        self.addChildren(params)
        self.itemDict={ 'show cursors':self.cursors,
                        'show X value':1,
                        'show Y value':2}

        #création des paramètres :
        self.sigTreeStateChanged.connect(self.updateGraph)
        """
        self.proxy = pg.SignalProxy(self.graph.scene().sigMouseMoved,rateLimit = 25,
                                    slot = self.mouseUpdate)
        """

    def setCurve(self,curve):

        self.leftLimit = 0
        self.rightLimit = 1
        self.curve = curve
        self.updateGraph(None,[[self.param('snap to selected signal'),None,
                                self.param('snap to selected signal').value()]])
        # plus besoin de la dernière position car le curseur_ctrl renvoi la position
        # dès la sélection d'une courbe
        """
        if self.lastPos is not None:
            self.mouseUpdate(self.lastPos)"""


    def mouseUpdate(self,x,y):
        """_summary_

        Args:
            evt (_type_): _description_
        """
        #pos = evt[0]

        if self.param('show cursors').value():
            #mousePoint = self.vb.mapSceneToView(pos)
            #! revoir cette partie
            if y is None:
                y=0
            pos=QtCore.QPointF(x,y)
            self.valtext.setPos(pos)

            self.cursors[0].setPos(x)
            self.cursors[1].setPos(y)
            text=[f'X={x:0.1f}',f'Y={y:0.1f}',
                    f'X={x:0.1f}\nY={y:0.1f}']
            if self.textIndex>=0:
                self.valtext.setText(text[self.textIndex])
            #self.lastPos=pos

    def updateSelection(self,item):
        #! passer la courbe à suivre
        pass

    def updateGraph(self,group,modifications):
        """Méthode permettant d'afficher ou non les curseurs en fonction de l'état
        logique du parameterTreeItem associé

        Args:
            changes (GroupParameter): GroupParameter dans lequel est intervenu la modification
            params (GraphicsObject): liste de tuples constitué du paramètre modifié, du type de
            modification et de la nouvelle valeur de ce paramètre
        """

        #on ne considère que la première modification : donc toujours fairee un elif avec cursor en
        #tête car cursor permet d'activer les 3 autres paramètres si un seul évènement provoquant
        #alors l'activation de toutes l'arborescence de if.

        parameter,_,value=modifications[0]
        key=parameter.name()
        if key=='show cursors':

            if value:
                self.blockSignals(True)
                self.param('snap to selected signal').setOpts(enabled=True)
                self.param('show X value').setOpts(enabled=True)
                self.param('show Y value').setOpts(enabled=True)
                self.blockSignals(False)
            else:
                self.blockSignals(True)
                self.param('snap to selected signal').setOpts(enabled=False)
                self.param('show X value').setOpts(enabled=False)
                self.param('show Y value').setOpts(enabled=False)
                self.param('snap to selected signal').setValue(False)
                if self.textIndex>=0:
                    self.param('show X value').setValue(False)
                    self.param('show Y value').setValue(False)
                    #retirer valtext du graph n'écrase pas le texte conservé dans cet objet
                    #ce qui pose problème lorsque celui-ci est de nouveau affiché
                    self.valtext.setText('')
                    self.graph.removeItem(self.valtext)
                    self.textIndex=-1
                self.blockSignals(False)

            plotItems=self.itemDict[key]
            for item in plotItems:
                if value:
                    self.graph.addItem(item, ignoreBounds=True)
                else:
                    self.graph.removeItem(item)

        elif key=='show X value' or key=='show Y value':
            if value:
                if self.textIndex<0:
                    self.graph.addItem(self.valtext)
                    if self.param('snap to selected signal').value() and \
                        self.curvePoint is not None:
                        #setParentItem ne semble fonctionner que si l'objet parent
                        #est chargé dans le graphe\scene
                        self.valtext.setParentItem(self.curvePoint)

                self.textIndex+=self.itemDict[key]
            else:
                self.textIndex-=self.itemDict[key]
                if self.textIndex<0:
                    self.valtext.setText('')
                    self.graph.removeItem(self.valtext)

        elif key=='snap to selected signal':
            if value and self.curve is not None:
                if self.curvePoint is not None :
                    self.valtext.setParentItem(None)
                    self.graph.removeItem(self.curvePoint)

                self.curvePoint=pg.CurvePoint(self.curve)
                self.graph.addItem(self.curvePoint)
                curve_color=self.curve.opts['pen'].color()
                self.valtext.setColor(curve_color)
                self.cursors[0].setPen(curve_color)
                self.cursors[1].setPen(curve_color)
                self.valtext.setParentItem(self.curvePoint)

                #la position étant du texte étant définie par rapport à son parent
                #il faut retirer son ancienne position
                self.valtext.setPos(0,0)

            else:
                if self.curvePoint is not None:
                    self.valtext.setParentItem(None)
                    self.graph.removeItem(self.curvePoint)
                    default_color=(100,100,100)
                    self.valtext.setColor(default_color)
                    self.cursors[0].setPen(default_color)
                    self.cursors[1].setPen(default_color)
