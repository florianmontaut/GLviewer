"""
Module contenant des QWidgets et QDialog générique pouvant être chargés pour différents projet
"""
import csv
import pathlib

from collections import namedtuple
import numpy as np
from PyQt6.QtWidgets import (QFontDialog,QDialog,QColorDialog,QTabWidget,QGraphicsLineItem,
                            QGraphicsItem,QWidget,QTableWidget,QLineEdit,QCheckBox,QSpinBox,
                            QDoubleSpinBox,QGridLayout,QDialogButtonBox,QTableWidgetItem,
                            QGraphicsEllipseItem,QFormLayout,QLabel)
from PyQt6.uic import loadUi
from PyQt6 import QtGui,QtCore
from ressources import custom_struct_functions

import pyqtgraph.parametertree as ptree
import pyqtgraph as pg

from model.analysis import analysis_factory
from model.filters import filter_factory


PATH=pathlib.Path(__file__).parent


class OptionsPannel(QDialog):
    """
    Options pannel généré AUTOMATIQUEMENT à partir du PARAMETER_SCHEMA
    (une tab par setting)
    """

    def __init__(self, schema, saved_options=None, parent=None):
        super().__init__(parent)
        self.setWindowIcon(QtGui.QIcon(str(PATH)+'/icon.ico'))
        #Load the UI Page
        loadUi(PATH/'Custom_options.ui', self)
        self.saved_options = saved_options or {}
        self.schema = schema
        self.tabWidget:QTabWidget

        self.parameter_roots = {}     # setting → Parameter
        self.opts_dicts = {}          # setting → opts_dict
        self._build_tabs()
        self._restore_saved_options()
        self.buttonBox:QDialogButtonBox
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
    # ------------------------------------------------

    def _restore_saved_options(self):
        for setting, param_root in self.parameter_roots.items():
            custom_struct_functions.apply_options_to_parameters(
                                                param_root,
                                                self.opts_dicts[setting],
                                                self.saved_options
                                            )

    def _build_tabs(self):

        for setting_name, setting_schema in self.schema.items():

            tab=QWidget()
            gridLayout = QGridLayout(tab)
            gridLayout.setContentsMargins(5, 5, 5, 5)
            tree_widget = ptree.ParameterTree(parent=tab)
            tree_widget.setHeaderHidden(True)
            tree_widget.setIndentation(20)
            tree_widget.setObjectName("PannelWidget")
            tree_widget.headerItem().setText(0, "1")
            gridLayout.addWidget(tree_widget,0, 0, 1, 1)
            # génération ParameterTree
            param_root = self.build_parameter_group(
                                                        setting_name,
                                                        setting_schema.get("children", {})
                                                    )
            tree_widget.setParameters(param_root, showTop=False)
            # stockage pour récup ultérieure
            self.parameter_roots[setting_name] = param_root
            # génération automatique opts_dict pour CE setting
            self.opts_dicts[setting_name] = (custom_struct_functions.generate_opts_dict(
                                                                setting_schema.get("children",
                                                                                    {})))
            self.tabWidget.addTab(tab, setting_name)

    # ------------------------------------------------
    # API publique
    # ------------------------------------------------

    def getOptions(self):
        """
        Retourne un dictionnaire plat :
        { logical_key: value }
        """
        result = {}

        for setting, param_root in self.parameter_roots.items():
            opts = custom_struct_functions.extract_parameter_values(
                                                    param_root,
                                                    self.opts_dicts[setting]
                                                )
            result.update(opts)

        return result

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




class TextDialog(QDialog):
    """
    Classe héritant de QDialog, permettant d'avoir un utilitaire de mise en forme de texte
    """
    def __init__(self,text=None,font=None,color=None,*args,**kwargs):
        QDialog.__init__(self,*args,**kwargs)
        self.setWindowIcon(QtGui.QIcon(str(PATH)+'/icon.ico'))
        #Load the UI Page
        loadUi(PATH/'TextWindow.ui', self)
        self.fontB.clicked.connect(self.fontChoice)
        self.colorB.clicked.connect(self.colorChoice)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        self.setModal(True)

        #si font précisé, on le charge (tout cela est nécesaire car le chargement du code html
        #ne semble pas être compatible avec l'éditeur de font :
        #le taille du caractère n'est plus modifiable)
        if font is not None:
            self.textEdit.setFont(font)
        if color is not None:#si color précisé, on le charge
            self.textEdit.setTextColor(color)
            self.color=color
        if text is not None:#si text précisé, on le charge
            self.textEdit.setText(text)

    def fontChoice(self):
        """
        Méthode gérant la police du texte
        """

        initial_font = self.textEdit.currentFont()
        font, valid =QFontDialog.getFont(initial_font)
        if valid:
            self.textEdit.setFont(font)

    def colorChoice(self):
        """
        Méthode gérant le choix de la couleur du texte
        """
        color =QColorDialog.getColor(self.textEdit.textColor())
        if color.isValid():
            self.textEdit.setTextColor(color)

    def getText(self):
        """Méthode retournant le texte en html, sa police et sa couleur

        Returns:
            _type_: _description_
        """

        return self.textEdit.toHtml(),self.textEdit.font(),self.textEdit.textColor()


    def showEvent(self, event):
        super().showEvent(event)
        self.textEdit.setFocus()
        self.textEdit.selectAll()
        self.textEdit.moveCursor(QtGui.QTextCursor.MoveOperation.End)

    #en plus du html qui contient tout les éléments nécessaire, on envoie également le font
    #et la couleur afin de faciliter le renvoie de ces mêmes
    #information au prochaine chargement de la fenêtre


class ScaleDialog(QDialog):
    """
    Classe héritant de QDialog, permettant d'avoir un utilitaire récupérant les paramètres
    d'un repère orthonormé
    """

    def __init__(   self,
                    Xmin = None,
                    Xmax = None,
                    Ymin = None,
                    Ymax = None,
                    logX = None,
                    logY = None,*args,**kwargs):

        QDialog.__init__(self,*args,**kwargs)
        self.setWindowIcon(QtGui.QIcon(str(PATH)+'/icon.ico'))
        #Load the UI Page
        loadUi(PATH/'ScaleDialog.ui', self)
        if Xmin is not None:
            self.XminEdit.setText(str(Xmin))
        if Xmax is not None:
            self.XmaxEdit.setText(str(Xmax))
        if Ymin is not None:
            self.YminEdit.setText(str(Ymin))
        if Ymax is not None:
            self.YmaxEdit.setText(str(Ymax))
        if logX is not None:
            if logX:
                self.XAxisLog.setChecked(True)
        if logY is not None:
            if logY:
                self.YAxisLog.setChecked(True)

        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        #sélection le champ complet XminEdit lors de l'ouverture de la fenêtre ScaleDialog
        #(plus pratique pour réécrire directement la valeur souhaitée)
        self.XminEdit.selectAll()

    def getValues(self):
        """
        Méthode assurant la mise en forme des entrées de l'utilisateur
        Returns:
            {float,float,float,bool,bool} --    structure contenant les informations du repère
                                                orthonormé
        """
        #remplace le séparateur décimal par un point
        #(compatiblité avec le float, on pourrait modifier la variable global "locale"
        xmin=self.XminEdit.text().replace(',', '.')
        xmax=self.XmaxEdit.text().replace(',', '.')
        ymin=self.YminEdit.text().replace(',', '.')
        ymax=self.YmaxEdit.text().replace(',', '.')

        return (float(xmin),float(xmax),
                float(ymin),float(ymax),
                self.XAxisLog.isChecked(),self.YAxisLog.isChecked())
    #en plus du html qui contient tout les éléments nécessaire,
    #on envoie également le font et la couleur afin de faciliter le renvoie de ces mêmes
    #information au prochaine chargement de la fenêtre





class AnchorHandle(QGraphicsEllipseItem):

    def __init__(self, radius=4, color=QtGui.QColor("red"), owner=None):
        super().__init__(-radius, -radius, 2*radius, 2*radius)

        self.owner = owner

        self.setBrush(color)
        #self.setPen(pg.mkPen(QtCore.Qt.PenStyle.NoPen))
        self.setZValue(9)

        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
            QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges |
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        )

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            if self.owner is not None:
                self.owner.update_arrow()
        return super().itemChange(change, value)



class pgText(pg.TextItem):

    def __init__(self,plotItem,text=None,anchor_pos=None,*args,**kwargs):

        super().__init__(*args,**kwargs)
        #ItemIsMovable remplace la fonction MouseDragEvent
        self.plotItem = plotItem
        self.setFlags(  QGraphicsItem.GraphicsItemFlag.ItemIsFocusable |
                        QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                        QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        if text is not None:
            self.setText(text)
        #flag ne permettant l'ouverture que d'une seule fenêtre par pgTextitem en même temps
        self.Onflag=False
        self.font=QtGui.QFont("Times", 8)
        self.color=kwargs.get("color",QtGui.QColor("black"))

        # Point exact à annoter
        self.anchor_pos = anchor_pos

        # Flèche
        self.arrow = None
        self.anchorHandle = None
        self.lineItem = None
        self.setZValue(10)

    def keyPressEvent(self, event):
        """
        Méthode dédié à l'apparition d'une entrée du clavier
        Args:
            event (QEvent): entrée clavier
        """

        if event.key() == QtCore.Qt.Key.Key_Delete | self.hasFocus():
            #//TODO : l'élément est caché pour l'instant (il devrait être
            #//TODO détruit mais je ne sais l'implémenter)
            self.hide()
        event.accept()

    def mousePressEvent(self,ev):
        """Méthode dédié à l'apparition d'un clic de la souris
        Args:
            event (QEvent): entrée clic souris
        """
        if ev.button() != QtCore.Qt.MouseButton.LeftButton :
            ev.ignore()
        else:
            ev.accept()

    def mouseDoubleClickEvent(self,ev):
        """
        Méthode dédié à l'apparition d'un double-clic de la souris
        Args:
            event (QEvent): entrée double-clic souris
        """
        if not self.Onflag: #si fenêtre déjà ouverte on sort de la fonction
            self.Onflag=True #mise à 1 du flag éditeur ouvert
            self.textEditor()
            self.Onflag=False #on est sorti de l'éditeur, mise à 0 du flag
        ev.accept()

    def textEditor(self):
        """
        Méthode gérant l'apparition de la fenêtre de modification du texte
        """
        if self.toPlainText() is not None:
            self.window=TextDialog(text=self.toPlainText(),font=self.font,color=self.color)
        else:
            self.window=TextDialog()
        self.window.show()
        #si OK est pressé dans la dialogBox, on récupère les données
        def updateText():
            html,self.font,self.color=self.window.getText()
            self.setHtml(html)
        self.window.accepted.connect(updateText)

    '''
    def addArrow(self):
        """
        #! A CODER
        Méthode gérant la création d'une flêche reliant le text à la courbe parent
        """
        g = pg.GraphItem()
        ## Define positions of nodes:
        # 1er point = position x,y sur la courbe
        # 2eme point = position x,y du texte
        pos = np.array([ [0,0], [10,0]])
        ## Define the set of connections in the graph
        adj = np.array([[0,1]])

        ## Define the symbol to use for each node (this is optional)
        ## Define the line style for each connection (this is optional)
        lines = (255,0,0,255)

        ## Update the graph
        g.setData(pos=pos, adj=adj, pen=lines, size=0,  pxMode=False)
    '''

    # -----------------------------------------------------
    # Création de la flèche
    # -----------------------------------------------------


    def createArrow(self):
        if self.anchor_pos is None:
            return

        # Ligne
        self.lineItem = QGraphicsLineItem()
        self.lineItem.setPen(QtGui.QPen(self.color, 1))
        self.lineItem.setZValue(self.zValue() - 2)

        # Tête de flèche
        self.arrow = pg.ArrowItem(
                                    headLen=10,
                                    tipAngle=30,
                                    baseAngle=20,
                                    pen=pg.mkPen(self.color),
                                    brush=self.color
                                )
        self.arrow.setZValue(self.zValue() - 1)

        # Ancrage
        self.anchorHandle = AnchorHandle(
                                            color=self.color,
                                            owner=self
                                        )

        self.plotItem.addItem(self.lineItem)
        self.plotItem.addItem(self.arrow)
        self.plotItem.addItem(self.anchorHandle)

        self.anchorHandle.setPos(*self.anchor_pos)
        self.update_arrow()

    # -----------------------------------------------------
    # Mise à jour de la flèche
    # -----------------------------------------------------


    def _roiCornersScene(self):
        """
        Retourne les 4 coins du ROI du texte en coordonnées scene
        """
        rect = self.boundingRect()

        corners_local = [
            rect.topLeft(),
            rect.topRight(),
            rect.bottomLeft(),
            rect.bottomRight()
        ]

        return [self.mapToScene(p) for p in corners_local]


    def _closestCornerToAnchor(self):
        anchor_pos = self.anchorHandle.scenePos()
        corners = self._roiCornersScene()

        distances = [
            (corner, QtCore.QLineF(corner, anchor_pos).length())
            for corner in corners
        ]

        return min(distances, key=lambda x: x[1])[0]



    def update_arrow(self):
        if not self.lineItem or not self.arrow or not self.anchorHandle:
            return

        anchor_pos = self.anchorHandle.scenePos()

        # Coin du ROI optimal
        start_point = self._closestCornerToAnchor()

        # Ligne finie
        line = QtCore.QLineF(start_point, anchor_pos)
        self.lineItem.setLine(line)

        # Orientation flèche
        dx = line.dx()
        dy = line.dy()
        angle = -np.degrees(np.arctan2(dy, dx))

        self.arrow.setPos(anchor_pos)
        self.arrow.setStyle(angle=angle)

    # -----------------------------------------------------
    # Callback automatique lors d’un déplacement
    # -----------------------------------------------------


    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.update_arrow()
        return super().itemChange(change, value)


    # -----------------------------------------------------
    # Suppression propre
    # -----------------------------------------------------

    def delete(self):
        if self.arrow:
            self.plotItem.removeItem(self.arrow)
        if self.anchorHandle:
            self.plotItem.removeItem(self.anchorHandle)
        self.plotItem.removeItem(self)





class ImportErrorDialog(QDialog):
    """
    Classe héritant de QDialog, permettant de proposer à l'utilisateur de
    changer de fonction pour importer le fichier
    """

    def __init__(self,error,importFormats,currentFormat,*args,**kwargs):

        QDialog.__init__(self,*args,**kwargs)
        self.setWindowIcon(QtGui.QIcon(str(PATH)+'/icon.ico'))
        #Load the UI Page
        loadUi(PATH/'ImportError.ui', self)
        self.formats_dict=importFormats
        #on retire le format d'import ayant échoué de la liste des choix
        self.formats=[val for format,val in self.formats_dict.items() if format != currentFormat]
        self.comboBox.addItems(self.formats)
        self.ErrorText.setText( "Error, can't load the selected file:"+
                                "\n\r\n\r\"{error}\"\n\r\n\rTry using a new format:")
        #! attention le lien entre la buttonBox et la fenêtre de dialogue a été
        # généré dans le QtDesigner, les lignes ci-dessous font doublons
        #self.buttonBox.accepted.connect(self.accept)
        #self.buttonBox.rejected.connect(self.reject)
        #fige le reste de l'application.
        self.setModal(True)

    def getFormat(self):
        """
        Méthode assurant la mise en forme des entrées de l'utilisateur
        Returns:
            {float,float,float,bool,bool} --    structure contenant les informations du repère
                                                orthonormé
        """
        #remplace le séparateur décimal par un point
        out=None
        for key,val in self.formats_dict.items():
            if val == self.formats[self.comboBox.currentIndex()]:
                out=key
        return out



class ImportWizardDialog(QDialog):
    """
    Classe héritant de QDialog, permettant de proposer à l'utilisateur de changer
    de choisir et visualiser l'import de fichier .csv/.txt
    """
    params_ready = QtCore.pyqtSignal(dict)
    HIGHLIGHT_BRUSH = QtGui.QBrush(QtGui.QColor(220, 235, 255))  # bleu clair
    DEFAULT_BRUSH = QtGui.QBrush(QtCore.Qt.GlobalColor.white)

    def __init__(self, adress, delimitor:str=';',unitDelim:str=",",*args,**kwargs) :

        QDialog.__init__(self,*args,**kwargs)
        self.setWindowIcon(QtGui.QIcon(str(PATH)+'/icon.ico'))
        #Load the UI Page
        loadUi(PATH/"importTxtDialog.ui",self)
        self.rawfile=adress
        self.DelimitorEdit : QLineEdit
        self.UnitEdit : QLineEdit
        self.NameBox : QCheckBox
        self.TimeBox : QCheckBox
        self.importTable : QTableWidget
        self.buttonBox : QDialogButtonBox

        self.DelimitorEdit.setPlaceholderText(delimitor)
        self.UnitEdit.setPlaceholderText(unitDelim)
        self.DelimitorEdit.editingFinished.connect(self.newImportConfig)
        self.UnitEdit.editingFinished.connect(self.newImportConfig)
        self.NameBox.setCheckState(QtCore.Qt.CheckState.Checked)
        self.TimeBox.setCheckState(QtCore.Qt.CheckState.Checked)
        #En forçant l'argument init=True, on passe le test de changement des délimiteurs
        #dans la méthode newImportConfig
        self.NameBox.toggled.connect(lambda: self.newImportConfig(True))
        self.delimitor=delimitor
        self.unitDelim=unitDelim

        # Données chargées (liste de listes de str)
        self.data = []          # matrice d'origine (sans ligne/col de checkboxes)
        self.n_rows = 0         # nb de lignes de données
        self.n_cols = 0         # nb de colonnes de données

        # Sélections (indices dans le QTableWidget avec décalage +1)
        self.selected_rows = set()   # indices de lignes dans le QTableWidget (>= 1)
        self.selected_cols = set()   # indices de colonnes dans le QTableWidget (>= 1)
        self.row_flag=False
        self.importTable.verticalHeader().setVisible(False)
        self.importTable.horizontalHeader().setVisible(False)
        self.newImportConfig(True)
        self.setModal(True)


    def newImportConfig(self,init=False) -> None:


        def _normalize_delimiter( text: str) -> str:
            text = text.strip()
            if text == r"\t":
                return "\t"
            if text == r"\n":
                return "\n"
            if text == r"\r":
                return "\r"

            return text

        outTxt=[]
        if self.DelimitorEdit.text() != "":
            newDelim=self.DelimitorEdit.text()
        else:
            newDelim=self.DelimitorEdit.placeholderText()

        if self.UnitEdit.text() != "":
            newUnit=self.UnitEdit.text()
        else:
            newUnit=self.UnitEdit.placeholderText()

        if newUnit==self.unitDelim and newDelim==self.delimitor and not init:
            return
        else:
            self.delimitor=_normalize_delimiter(newDelim)
            self.DelimitorEdit.setPlaceholderText(self.delimitor)
            self.unitDelim=newUnit
            self.UnitEdit.setPlaceholderText(newUnit)

        with open(self.rawfile,encoding="utf-8-sig") as f :

            rawtxt = csv.reader(f, delimiter=self.delimitor)
            for n,line in enumerate(rawtxt):
                if n>49:
                    break
                try:
                    outTxt.append(  [float(element.replace(self.unitDelim,'.'))
                                    for element in line])
                except:
                    outTxt.append(line)
                    continue

            self.populate_table(outTxt)

    def collect_params(self) -> list:
        """
        Méthode assurant la mise en forme des entrées de l'utilisateur
        Returns:
            {float,float,float,bool,bool} --    structure contenant les informations du repère
                                                orthonormé
        """
        # on retire 1 aux valeurs des colonnes et lignes car la première
        # ligne et colonne sont occupées par des cases à côcher faussant
        # la valeur des index correspondant aux données du fichier
        # de plus pour les columns on ne transmet que la valeur des colonnes
        # à ignorer (simplifie la gestion lorsque l'utilisateur n'en retire aucunne)

        allColumns=set(range(1,self.n_cols+1))
        ignoredColumns=allColumns-self.selected_cols
        ignoredColumns=[val-1 for val in ignoredColumns]

        return {'delim'           : self.delimitor,
                'unitdelim'       : self.unitDelim,
                'start'           : sorted(self.selected_rows)[0]-1,
                'columns'         : ignoredColumns,
                'sigNames'        : True if  self.NameBox.checkState()
                                            == QtCore.Qt.CheckState.Checked else False,
                'isFirstColIndex' : True if self.TimeBox.checkState()
                                            == QtCore.Qt.CheckState.Checked else False
                }


    def populate_table(self,txt):
        """
        Remplit le QTableWidget avec :
        - +1 ligne en tête pour les checkbox de colonnes (index 0)
        - +1 colonne en tête pour les checkbox de lignes  (index 0)
        Les données sont placées à partir de (1, 1).
        """

        # Normalisation des lignes (rectangulaire)
        names=None
        max_cols = max((len(r) for r in txt), default=0)
        for r in txt:
            if len(r) < max_cols:
                r.extend([""] * (max_cols - len(r)))


        if self.NameBox.checkState()==QtCore.Qt.CheckState.Checked:
            names=txt.pop(0)

        self.n_rows = len(txt)
        self.n_cols = max_cols
        self.importTable.clear()
        self.importTable.setRowCount(self.n_rows + 1)
        self.importTable.setColumnCount(self.n_cols + 1)
        # Réinitialiser la sélection
        self.selected_rows.clear()
        self.selected_cols.clear()

        # Cellule (0,0) : label d'aide
        help_item = QTableWidgetItem("✓")
        help_item.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled)  # pas sélectionnable
        help_item.setToolTip(   "Cases à cocher en première ligne"+
                                "(colonnes) et première colonne (lignes).")
        self.importTable.setItem(0, 0, help_item)


        # Première ligne : checkboxes de colonnes
        for j in range(1, self.n_cols + 1):
            # import local pour clarté
            chkBoxItem = QTableWidgetItem()
            chkBoxItem.setFlags(QtCore.Qt.ItemFlag.ItemIsUserCheckable |
                                QtCore.Qt.ItemFlag.ItemIsEnabled)
            chkBoxItem.setCheckState(QtCore.Qt.CheckState.Checked)
            if names is not None:
                chkBoxItem.setText(names.pop(0))
            else:
                chkBoxItem.setText("")
            self.importTable.setItem(0,j,chkBoxItem)
            self.selected_cols.add(j)

        # Première colonne : checkboxes de lignes
        for i in range(1, self.n_rows + 1):
            chkBoxItem = QTableWidgetItem()
            chkBoxItem.setFlags(QtCore.Qt.ItemFlag.ItemIsUserCheckable |
                                QtCore.Qt.ItemFlag.ItemIsEnabled)
            chkBoxItem.setCheckState(QtCore.Qt.CheckState.Checked)
            self.importTable.setItem(i,0,chkBoxItem)
            self.selected_rows.add(i)

        # Données
        for i in range(self.n_rows):
            for j in range(self.n_cols):
                item = QTableWidgetItem(str(txt[i][j]))
                # sélection désactivée, on gère le highlight
                item.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled)
                item.setBackground(self.DEFAULT_BRUSH)
                self.importTable.setItem(i + 1, j + 1, item)

        self.importTable.itemClicked.connect(self.checkbox_changed)
        self.repaint_selection()

    # -------------------------
    # Gestion des sélections
    # -------------------------
    def checkbox_changed(self,item):
        """
        row_index_in_table : index dans le QTableWidget (>=1)
        """
        # 2 correspont à l'état Qt.CheckState.Checked, i.e l'état d'une case cochée
        # on utilise cet entier plutôt que Qt.CheckState car la boite de dialog
        # semble renvoyer un int
        if item.column()==0:
            if item.checkState() == QtCore.Qt.CheckState.Checked :

                    if self.row_flag:
                        return
                    self.row_flag = True

                    for val in range(self.n_rows+1):
                        if val >= item.row() and val not in self.selected_rows:
                            self.selected_rows.add(val)
                            ohterItem = self.importTable.item(val, 0)
                            self.importTable.blockSignals(True)
                            ohterItem.setCheckState(QtCore.Qt.CheckState.Checked)
                            self.importTable.blockSignals(False)
                    self.row_flag=False
            else:
                for val in sorted(self.selected_rows):
                    if val <= item.row() :
                        self.selected_rows.discard(val)
                        ohterItem = self.importTable.item(val, 0)
                        self.importTable.blockSignals(True)
                        ohterItem.setCheckState(QtCore.Qt.CheckState.Unchecked)
                        self.importTable.blockSignals(False)

        elif item.row()==0:

            if item.checkState() == QtCore.Qt.CheckState.Checked:
                self.selected_cols.add(item.column())
            else:
                self.selected_cols.discard(item.column())

        else:
            return
        self.repaint_selection()

    def repaint_selection(self):
        """
        Met à jour le fond des cellules en fonction des lignes/colonnes sélectionnées.
        """
        # On parcourt uniquement la zone des données (i>=1, j>=1)
        rows = range(1, self.n_rows + 1)
        cols = range(1, self.n_cols + 1)

        for i in rows:
            row_selected = i in self.selected_rows
            for j in cols:
                col_selected = j in self.selected_cols
                item = self.importTable.item(i, j)
                if item is None:
                    continue
                if row_selected and col_selected:
                    item.setBackground(self.HIGHLIGHT_BRUSH)
                else:
                    item.setBackground(self.DEFAULT_BRUSH)

    def accept(self):
        params = self.collect_params()
        self.params_ready.emit(params)
        print(f'params sent! :{params.items()}')
        super().accept()

#! non exploité
class AnalysisParamsDialog(QDialog):

    params_ready = QtCore.pyqtSignal(dict)

    def __init__(self, missing_params,action_type):
        super().__init__()
        self._widgets = {}
        self._build_ui(missing_params,action_type)

    def accept(self):
        params = self.collect_params()

        self.params_ready.emit(params)
        super().accept()

    def _build_ui(self, missing_params,action_type):
        self.setWindowTitle("Missing parameters")

        layout = QFormLayout(self)
        if action_type in filter_factory.FilterFactory.REGISTRY:
            action = filter_factory.FilterFactory.REGISTRY[action_type]
        else:
            action = analysis_factory.AnalysisFactory.REGISTRY[action_type]

        schema = action.PARAMETER_SCHEMA
        self.opts_dicts = custom_struct_functions.generate_opts_dict(schema=schema)

        for label, spec in schema.items():

            key = spec["key"]
            if key not in missing_params:
                continue  # on ne crée des champs QUE pour les paramètres manquants
            ptype    = spec.get("type", "float")
            default  = spec.get("default")
            limits   = spec.get("limits", (None, None))
            suffix   = spec.get("suffix", "")
            readonly = spec.get("readonly", False)

            pmin, pmax = limits

            # -------- Widget selection --------
            if ptype == "int":
                widget = QSpinBox()
                widget.setMinimum(pmin if pmin is not None else -2**31)
                widget.setMaximum(pmax if pmax is not None else  2**31 - 1)
                if default is not None:
                    widget.setValue(default)

            elif ptype == "float":
                widget = QDoubleSpinBox()
                widget.setDecimals(6)
                widget.setMinimum(pmin if pmin is not None else -1e12)
                widget.setMaximum(pmax if pmax is not None else  1e12)
                if default is not None:
                    widget.setValue(default)

            else:
                widget = QLineEdit()
                if default is not None:
                    widget.setText(str(default))

            if suffix and hasattr(widget, "setSuffix"):
                widget.setSuffix(f" {suffix}")

            widget.setReadOnly(readonly)

            self._widgets[key] = widget
            layout.addRow(label, widget)

        # -------- Buttons --------
        buttons = QDialogButtonBox(
                                    QDialogButtonBox.StandardButton.Ok |
                                    QDialogButtonBox.StandardButton.Cancel
                                    )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def collect_params(self):
        params = {}
        for key, widget in self._widgets.items():
            #key=self.opts_dicts[name]
            if isinstance(widget, QSpinBox):
                params[key] = widget.value()
            elif isinstance(widget, QDoubleSpinBox):
                params[key] = widget.value()
            else:
                params[key] = widget.text()
        return params
