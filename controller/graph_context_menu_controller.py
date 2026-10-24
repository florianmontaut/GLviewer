from PyQt6 import QtCore,QtGui,QtWidgets
from dataclasses import dataclass

from model.base_objects import SignalObject
from ressources.custom_menu import BaseContextMenu
from ressources.custom_types import qSignalType



class GraphContextMenu(BaseContextMenu):


    def __init__(self, plot, action_callback):
        self.plot = plot
        menu : QtWidgets.QMenu = plot.vb.menu
        super().__init__(menu, action_callback)

    def _build_menu(self):
        isolate     = self._add_action(qSignalType.ISOLATE)
        ref_        = self._add_action(qSignalType.REF)
        filter_     = self._add_action(qSignalType.FILTER)
        delta_      = self._add_action(qSignalType.DIFF)
        y_offset    = self._add_action(qSignalType.OFFSET)
        x_offset    = self._add_action(qSignalType.OFFSET_X)
        model_      = self._add_action(qSignalType.MODEL)
        text_       = self._add_action(qSignalType.TEXT)
        delete_     = self._add_action(qSignalType.DEL)
        start_rec   = self._add_action(qSignalType.START)
        stop_rec    = self._add_action(qSignalType.STOP)

        view_all = self.menu.actions()[0]
        self.menu.insertActions(   view_all,
                                    [
                                        isolate,
                                        ref_, filter_,
                                        delta_,
                                        y_offset,
                                        x_offset,
                                        model_,
                                        text_,
                                        delete_]
                                )
        self.menu.insertSeparator(view_all)
        self.menu.insertSeparator(filter_)

        self.macro_menu = self._add_submenu("Macro",delete_)
        #? bug du menu contextuel, les actions et sous menu ne semblent plus s'afficher ou s'activer correctement
        #? il semble que le problème n'apparaisse pas avec un seul niveau de sous menu, il faudrait tester pour voir
        #? si c'est lié à la profondeur du menu ou au nombre d'actions présentes
        #self.apply_macro_menu = self._add_submenu("Use Macro",self.macro_menu)
        self.macro_menu.addActions([start_rec,stop_rec])
        self.menu.insertSeparator(delete_)
        self.macro_menu.addSeparator()


    def add_macro_action(self, macro):
        action = QtGui.QAction(macro.name, self.macro_menu)
        action.triggered.connect(
                                    lambda _, name=macro.name:
                                        self._action_callback(qSignalType.MACRO, name)
                                )
        self.macro_menu.addAction(action)
