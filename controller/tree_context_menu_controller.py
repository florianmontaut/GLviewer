from PyQt6 import QtCore,QtGui,QtWidgets
from dataclasses import dataclass

from model.base_objects import SignalObject
from ressources.custom_types import qSignalType
from ressources.custom_menu import BaseContextMenu


class TreeContextMenu(BaseContextMenu):

    def __init__(self, tree: QtWidgets.QTreeView, action_callback):
        self.tree = tree
        menu = QtWidgets.QMenu(tree)
        super().__init__(menu, action_callback)

        tree.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        tree.customContextMenuRequested.connect(self._on_context_menu)

    def _build_menu(self):
        isolate  = self._add_action(qSignalType.ISOLATE)
        ref_     = self._add_action(qSignalType.REF)
        filter_  = self._add_action(qSignalType.FILTER)
        delta_   = self._add_action(qSignalType.DIFF)
        y_offset = self._add_action(qSignalType.OFFSET)
        x_offset = self._add_action(qSignalType.OFFSET_X)
        model_   = self._add_action(qSignalType.MODEL)
        delete_  = self._add_action(qSignalType.DEL)
        start_rec = self._add_action(qSignalType.START)
        stop_rec  = self._add_action(qSignalType.STOP)

        self.menu.addActions([
                                isolate,
                                ref_,
                                filter_,
                                delta_,
                                y_offset,
                                x_offset,
                                model_,
                                delete_
                            ])
        self.menu.insertSeparator(filter_)
        self.macro_menu = self._add_submenu("Macro",delete_)
        self.menu.insertSeparator(delete_)
        #self.apply_macro_menu = self._add_submenu("Use Macro",self.macro_menu)
        #self.create_macro_menu = self._add_submenu("Create new Macro",self.macro_menu)
        self.macro_menu.addActions([start_rec,stop_rec])
        self.macro_menu.addSeparator()

    def _on_context_menu(self, pos):
        index = self.tree.indexAt(pos)
        if index.isValid():
            self.menu.exec(self.tree.viewport().mapToGlobal(pos))


    def add_macro_action(self, macro):

        action = QtGui.QAction(macro.name, self.macro_menu)
        action.triggered.connect(
                                    lambda _, name=macro.name:
                                    self._action_callback(qSignalType.MACRO, name)
                                )
        self.macro_menu.addAction(action)
