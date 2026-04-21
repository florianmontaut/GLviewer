import pandas as pd
from PyQt6 import QtCore,QtGui
from PyQt6.QtWidgets import QFileDialog,QHeaderView,QAbstractItemView
import pyqtgraph as pg
import pyqtgraph.parametertree as ptree
from ressources import (custom_dialogs,custom_tree_functions,custom_functions,custom_parameters,
                        custom_types,custom_struct_functions)

from model.base_objects import SignalObject

class GraphTreeController(QtCore.QObject):


    curve_selected          = QtCore.pyqtSignal(SignalObject)
    #menu_actions_triggered  = QtCore.pyqtSignal((custom_types.ActionModifier,
    #                                             custom_types.qSignalType))

    PARAMETER_SCHEMA = {
                        "Cursors menu": {
                                    "type": "group",
                                    "children":{
                                        "Cursors type":{
                                                    "type": "list",
                                                    "values":[  "Waveform",
                                                                "Horizontal bars",
                                                                "Vertical bars",
                                                                "H&V bars"
                                                                ],
                                                    "value":'Waveform',
                                                    "key": "cursor_type",
                                                    },
                                        'Vertical cursors':{
                                                    "type": "cursors",
                                                    "visible":False,
                                                    "expanded" : True,
                                                    "cursors_setting": {
                                                        'angle':90,
                                                        'pos':[1200,3600],
                                                        'pen':pg.mkPen(color = 'r'),
                                                        'label':'{value:0.0f}s',
                                                        'labelOpts':
                                                            {'color': (200,0,0),
                                                            'fill':(200,200,200,100),
                                                            'movable': True}
                                                        },
                                                    "key": "ver_cursors",
                                                    },
                                        'Horizontal cursors':{
                                                    "type": "cursors",
                                                    "visible":False,
                                                    "expanded" : True,
                                                    "cursors_setting":  {
                                                        'angle':0,
                                                        'pos':[50,100],
                                                        'pen':pg.mkPen(color = 'y'),
                                                        'label':'T = {value:0.2f}°C',
                                                        'labelOpts':
                                                            {'color': (200,200,100),
                                                            'fill': (200,200,200,50),
                                                            'movable': True}
                                                        },
                                                    "key": "hor_cursors",
                                                    },
                                        "Mouse cursor":{
                                                    "type": "mouse",
                                                    "key": "mouse_cursor",
                                                    "expanded" : True
                                                    },
                                        }
                                    },
                        "Add text":{
                                    "type":"action",
                                    "key":"add_text"
                                }
                        }

    def __init__(self, plot : pg.PlotItem,tree:ptree ,**opts):
        """
        Méthode gérant l'initialisation du Widget GraphTree
        """
        self.graphPlot=plot
        self.graphTree=tree
        self.textItems=[]
        self.parameter_roots={}
        self.opts_dict=custom_struct_functions.generate_opts_dict(self.PARAMETER_SCHEMA)

        params_root = self.build_parameter_group("Graphics tools",self.PARAMETER_SCHEMA)
        self.parameter_roots=params_root
        self.params={}
        self.settings=opts
        self._cursor_old_state = custom_types.cursorType.WAVEFORM

        for name,key in self.opts_dict.items():

            if isinstance(name,tuple):
                self.params[key]=self.parameter_roots.param(*name)
            else:
                self.params[key]=self.parameter_roots.param(name)

            '''if child.get('children',None) is not None:
                new_group_param= {  self.opts_dict[(folder,name)]: graphTree_params.param() for name,
                                    spec in child.get('children').items() }
                self.params.update(new_group_param)
            '''
        self.graphTree.setParameters(self.parameter_roots, showTop=False)
        #self.params['add_text'].sigActivated.connect(lambda x :self.addText())
        #mouseCursor sert pour les curseurs (mis à jour ssi les curseurs sont actifs)
        self.mouseCursor : custom_parameters.MouseCursors = self.params['mouse_cursor']
        self.cursors_H : custom_parameters.LinkedCursors = self.params['hor_cursors']
        self.cursors_V : custom_parameters.LinkedCursors = self.params['ver_cursors']
        self.parameter_roots.sigTreeStateChanged.connect(lambda x : self.cursor_states(x))
        #mousePos est toujours actif et initialisé à 0,0
        self.mousePos=QtCore.QPointF(0,0)

    def cursor_states(self,change):
        CURSOR_STATES = {
                        "Waveform"         : custom_types.cursorType.WAVEFORM,
                        "Horizontal bars"  : custom_types.cursorType.H_BARS,
                        "Vertical bars"    : custom_types.cursorType.V_BARS,
                        "H&V bars"         : custom_types.cursorType.VH_BARS,
                        }
        new_state=CURSOR_STATES[self.params['cursor_type'].value()]

        if new_state == self._cursor_old_state:
            return
        self._cursor_old_state = new_state

        with self.parameter_roots.treeChangeBlocker():
            match new_state:
                case  custom_types.cursorType.WAVEFORM:
                    self.params['hor_cursors'].setOpts(visible=False,expanded=False)
                    self.params['ver_cursors'].setOpts(visible=True,expanded=True)
                case custom_types.cursorType.H_BARS:
                    self.params['hor_cursors'].setOpts(visible=True,expanded=True)
                    self.params['ver_cursors'].setOpts(visible=False,expanded=False)
                case custom_types.cursorType.V_BARS:
                    self.params['hor_cursors'].setOpts(visible=False,expanded=False)
                    self.params['ver_cursors'].setOpts(visible=True,expanded=True)
                case custom_types.cursorType.VH_BARS:
                    self.params['hor_cursors'].setOpts(visible=True,expanded=True)
                    self.params['ver_cursors'].setOpts(visible=True,expanded=True)

    #! voir si la méthode ci-dessous ne nécessite pas une méthode récursive pour les groupes imbriqués
    #! voir parameter_controller pour la construction des groupes imbriqués
    def build_parameter_group(self,name, schema):
        children = []

        for pname, spec in  schema.items():
            ptype = spec["type"]
            #la valeur actuelle sauvegardée dans le filter node est récupérée içi
            # -----------------------------
            # Signal selector (ComboBox)
            # -----------------------------
            # ---------- GROUP ----------

            if ptype == "group":
                    group = self.build_parameter_group(
                                                        name=pname,
                                                        schema=spec.get("children", {}),
                                                        )
                    group.setOpts(expanded=spec.get("expanded", True) )
                    children.append(group)
                    continue

            if ptype == "mouse":
                    param=custom_parameters.MouseCursors(name=pname,
                                                    graphWidget = self.graphPlot)
                    param.setOpts(expanded=spec.get("expanded", True) )
                    children.append(param)
                    continue

            if ptype == "cursors":
                
                param=custom_parameters.LinkedCursors(  
                                                    name=pname,
                                                    graphWidget = self.graphPlot,
                                                    cursors_setting = spec['cursors_setting']
                                                    )
                #param.setOpts(expanded=spec.get("expanded", True) )
                
                param.setOpts(**spec)
                children.append(param)
                continue

            # ---------- SIMPLE TYPES ----------
            param = {
                        "name":     pname,
                        "value":    spec.get("default",None)
                    }

            # Nettoyage
            param = {k: v for k, v in param.items() if v is not None}
            param.update(spec)
            children.append(ptree.Parameter.create(**param))

        return ptree.Parameter.create(
                                name=name,
                                type="group",
                                children=children
                                )


    def addText(self,parent=None,pos=None):
        """_summary_
        """
        if pos is None:
            pos=self.mouseCursor.valtext.pos()


        if      self.mouseCursor.param('show X value').value() or \
                self.mouseCursor.param('show Y value').value():
            text_str=self.mouseCursor.valtext.toPlainText()
        else:
            text_str=""

        if self.mouseCursor.param('snap to selected signal').value():
            #!actuellement curve=None
            curve=self.mouseCursor.curve
            color =  QtGui.QColor("black")
        else:
            color = QtGui.QColor("black")

        text_item = custom_dialogs.pgText(
                                        plotItem=self.graphPlot,
                                        text=text_str,
                                        color=color,
                                        anchor_pos=(pos.x(), pos.y())
                                        )


        self.graphPlot.addItem(text_item)
        #!La flèche ne reçoit pas les bonnes coordonnées et angles
        #text_item.createArrow()
        '''
        if parent is not None:
            text.setParentItem(parent)
            text.setPos(QtCore.QPointF(0,0))
        else:
            text.setPos(pos + QtCore.QPointF(20,20))
        '''
        text_item.textEditor()

    def update_settings(self,new_settings):

        self.settings.update(new_settings)

        for cursor in self.cursors_H.cursors:

            new_label='{value:0.0f}'+new_settings.get('Y_unit')
            cursor.label.setFormat(new_label)

        for cursor in self.cursors_V.cursors:

            new_label='{value:0.0f}'+new_settings.get('X_unit')
            cursor.label.setFormat(new_label)