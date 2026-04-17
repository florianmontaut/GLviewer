import json
from PyQt6  import QtGui,QtCore


def getJSONConfig(JSON_file)->dict:
    """
    Méthode permettant de convertir un fichier de config d'un objet CSVStructure
    vers un dictionnaire exploitable par GLviewer
    Args:
        JSON_file (str): fichier JSON stockant les données d'un enregistrement
    Returns:
        dict: dictionnaire contenant les informations relatives à l'enregistrement
        (filtrage/modèles/etc...)
    """
    CSV_params = []
    with open(JSON_file, 'r') as fichier_parametres:
    # Charge le fichier JSON dans une variable config
        config  =  json.load(fichier_parametres)
    for element in config:
        CSV_params.append(element)
    def convertToPyKeyWords(rawInput):
        """
        Méthode assurant la conversion des mots clés JSON en mots clés python
        Args:
            rawInput (_type_): _description_
        Returns:
            dict: dictionnaire nom/valeurs récupérer du parameterTree
        """
        #TODO: Ne prend pas en compte les limitations infinies du type [0,None] (i.e [0,+inf])
        #TODO: Il faudrait vérifier que None ne soit pas présent dès que l'option limit
        #TODO: est utilisée...
        KeyWords = {"False":False,
                    "false":False,
                    "True":True,
                    "true":True,
                    "None":None,
                    "Null":None,
                    "null":None}
        def recursiveConversion(raw):
            """Conversion récursive
            Args:
                raw (_type_): _description_
            Returns:
                _type_: _description_
            """
            out = []
            for element in raw:
                newParam = {}
                for key,val in element.items():
                    if key=='children':
                        newParam[key] = [recursiveConversion(element[key])]
                    elif isinstance(val,str):
                        if val in KeyWords.keys():
                            newParam[key] = KeyWords[val]
                        else:
                            newParam[key] = val
                    else:
                        newParam[key] = val
                out.append(newParam)
            return out
        return recursiveConversion(rawInput)
    def convertToDict(input_list):
        """
        Méthode interne assurant la conversion de liste à dictionnaire
        Args:
            input_list {list}: liste des paramètres et leur valeurs
        Returns:
            dict: dictionnaire name/valeur extrait du parameterTree
        """
        result = {}
        for element in input_list:
            result.update(element.items())
        return result
    return convertToDict(convertToPyKeyWords(CSV_params))

def GetParamsValues(data):
    """
    Méthode permettant d'envoyer les données entrées par l'utilisateur dans le parametrerTree
    Args:
        data (PyQtgraph.Parameter): groupe de "paramètres" du parametrerTree
    Returns:
        list(dict): dictionnaire contenant les informations relatives à l'enregistrement
        (filtrage/modèles/etc...)
    """
    params_dict=dict()
    def recursive_search(parent_item):
        """
        Méthode permettant de récupérer l'ensemble des champs d'un parameter tree et de les
        renvoyer sous forme de liste (les champs dont la valeur est nulle sont ignorés)
        Arguments:
                parent_item {str or tuple}  --  clés permettant de scrupter les
                                                valeurs des champs correspondants
        Returns:
                user_data {dict}   --   Dictionnaire contenant les informations nécessaire
                                        pour paramétrer l'objet HVAC
        """
        #print(parent_item,type(data.child(parent_item).value()))
        if isinstance(parent_item,tuple):
            if data.child(*parent_item).hasChildren():
                if isinstance(data.child(*parent_item).value(),QtGui.QPen):
                    params_dict[parent_item]=data.child(parent_item).value()
                else:
                    for key in data.child(*parent_item).keys():
                        new_key=(*parent_item,key)
                        val=data.child(*new_key).value()
                        if val is not None:
                            params_dict[*new_key]=val
                        if data.child(*new_key).hasChildren():
                            recursive_search(new_key)
            else:
                params_dict[parent_item]=data.child(parent_item).value()
        else:
            if data.child(parent_item).hasChildren():
                if isinstance(data.child(parent_item).value(),QtGui.QPen):
                    params_dict[parent_item]=data.child(parent_item).value()
                else:
                    for key in data.child(parent_item).keys():
                        if isinstance(parent_item,str):
                            new_key=(parent_item,key)
                        else:
                            new_key=(*parent_item,key)
                        val=data.child(*new_key).value()
                        if val is not None:
                            params_dict[*new_key]=val
                        if data.child(*new_key).hasChildren():
                            recursive_search(new_key)
            else:
                params_dict[parent_item]=data.child(parent_item).value()
        return params_dict
    #le dictionnaire params_dict ajoute les (keys/values) à chaque recursive_search
    for val in data.keys():
        recursive_search(val)
    return params_dict

def SetParamsValues(data,newSettings,default=True):
    """
    Méthode permettant d'envoyer les données entrées par l'utilisateur dans le parametrerTree
    Args:
        data        {PyQtgraph.Parameter} -- groupe de "paramètres" du parametrerTree
        newSettings {dict}                -- dictionnaire des nouvelles valeurs des paramètres
        default     {bool}                -- modifie également la valeur de défaut du paramètre
    Returns:
        list        {dict}           -- dictionnaire contenant les informations
                                        relatives à l'enregistrement (filtrage/modèles/etc...)
    """
    def SearchParam(parent_item):
        """
        Méthode permettant de retrouver le paramètre avec son nom pour
        lui affecter sa nouvelle valeur
        Arguments:
                parent_item {str or tuple}  -- clés du champs à modifier
        """
        if isinstance(parent_item,tuple):
            data.child(*parent_item).setValue(newSettings[*parent_item])
            if default:
                data.child(*parent_item).setDefault(newSettings[*parent_item])
        else:
            data.child(parent_item).setValue(newSettings[parent_item])
            if default:
                data.child(parent_item).setDefault(newSettings[parent_item])
    #le dictionnaire params_dict ajoute les (keys/values) à chaque recursive_search
    for key in newSettings.keys():
        SearchParam(key)



def generate_opts_dict(schema: dict,offset_key:str = None):
    """
    Génère automatiquement :
    (path tuple ou str) -> logical_key
    """
    opts_dict = {}

    def normalize_path(path):
        if isinstance(path, tuple):
            return path[0] if len(path) == 1 else path
        return path
    def recurse(node, path=()):
        for name, spec in node.items():
            current_path = path + (name,) if path else name
            if "key" in spec:
                current_path = normalize_path(path + (name,) if path else name)
                opts_dict[current_path] = spec["key"]
            if spec.get("type") == "group":
                recurse(
                            spec.get("children", {}),
                            current_path if isinstance(current_path, tuple)
                            else (current_path,)
                        )
    recurse(schema)
    if offset_key is not None:
        offset_dict={}
        for name,key in opts_dict:
            if isinstance(name,str):
                new_path=(offset_key,name)
            else:
                new_path=(offset_key,)+name
            offset_dict[new_path]=key
        opts_dict.clear()
        opts_dict.update(offset_dict)

    return opts_dict


def extract_parameter_values(param_root, opts_dict):
        extracted = {}

        def recurse(param, path=()):

            for child in param.children():
                new_path = path + (child.name(),)
                if child.hasChildren():
                    recurse(child, new_path)
                else:
                    key = new_path if len(new_path) > 1 else new_path[0]
                    if key in opts_dict:
                        extracted[opts_dict[key]] = child.value()

        recurse(param_root)
        return extracted

def apply_options_to_parameters(param_root, opts_dict, saved_options):
    """
    Injecte saved_options dans le ParameterTree en utilisant opts_dict
    """
    def normalize_path(path):
        """
        Normalise une clé de chemin :
        - tuple de longueur 1 → str
        - tuple >1 → tuple
        """
        if isinstance(path, tuple):
            return path[0] if len(path) == 1 else path
        return path

    def recurse(param, path=()):
        for child in param.children():
            new_path = path + (child.name(),)
            if child.hasChildren():
                recurse(child, new_path)
            else:

                key_path = normalize_path(new_path)
                if key_path in opts_dict:
                    logical_key = opts_dict[key_path]
                    if logical_key in saved_options:
                        child.setValue(saved_options[logical_key])
    recurse(param_root)

def dict_to_QPen(data):
    """
    Reconstruit un QPen à partir d'un dictionnaire.
    """
    def _qt_enum(enum_cls, value):
        """Méthode nécessaire pour récupérer les QtEnum valables sans messages d'erreur

        Args:
            enum_cls (Enum): classe de type Enum
            value (str): clé/nom d'un élément de l'Enum que l'on souhaite récupérer

        Returns:
            Enum:   renvoi une valeur de l'Enum correspondant à la clé passée en attribut
                    (Enum.item)
        """
        return enum_cls(int(value))

    pen = QtGui.QPen()
    pen.setStyle(_qt_enum(QtCore.Qt.PenStyle,data["style"]))
    pen.setColor(QtGui.QColor(data["color"]))
    pen.setWidthF(data["width"])
    pen.setDashPattern(data["dash"])
    pen.setCosmetic(data["cosmetic"])
    pen.setCapStyle(_qt_enum(QtCore.Qt.PenCapStyle,data["cap"]))
    pen.setJoinStyle(_qt_enum(QtCore.Qt.PenJoinStyle,data["join"]))

    return pen


def dict_to_QPen(data):
    """
    Reconstruit un QPen à partir d'un dictionnaire.
    """
    def _qt_enum(enum_cls, value):
        """Méthode nécessaire pour récupérer les QtEnum valables sans messages d'erreur

        Args:
            enum_cls (Enum): classe de type Enum
            value (str): clé/nom d'un élément de l'Enum que l'on souhaite récupérer

        Returns:
            Enum:   renvoi une valeur de l'Enum correspondant à la clé passée en attribut
                    (Enum.item)
        """
        return enum_cls(int(value))

    pen = QtGui.QPen()
    pen.setStyle(_qt_enum(QtCore.Qt.PenStyle,data["style"]))
    pen.setColor(QtGui.QColor(data["color"]))
    pen.setWidthF(data["width"])
    pen.setDashPattern(data["dash"])
    pen.setCosmetic(data["cosmetic"])
    pen.setCapStyle(_qt_enum(QtCore.Qt.PenCapStyle,data["cap"]))
    pen.setJoinStyle(_qt_enum(QtCore.Qt.PenJoinStyle,data["join"]))

    return pen

def QPen_to_dict(pen):

    pen_args={
                'style'     :   pen.style().value,
                'color'     :   pen.color().name(QtGui.QColor.NameFormat.HexArgb),
                'width'     :   pen.widthF(),
                'dash'      :   pen.dashPattern(),
                'cosmetic'  :   pen.isCosmetic(),
                'cap'       :   pen.capStyle().value,
                'join'      :   pen.joinStyle().value,
            }
    return pen_args

def QColor_to_dict(color):

    color_args={
                'color'     :   color.name(QtGui.QColor.NameFormat.HexArgb),
            }
    return color_args

def dict_to_QColor(data):
    """
    Reconstruit un QColor à partir d'un dictionnaire.
    """

    return QtGui.QColor(data['color'])


if __name__ == "__main__":

    PARAMETER_SCHEMA = {
                    "X axis": {
                        "type": "group",
                        "children": {
                            "X axis title": {
                                "type": "str",
                                "default": "Temps",
                                "key": "X_title",
                            },
                            "X axis unit": {
                                "type": "str",
                                "default": "s",
                                "key": "X_unit",
                            },
                            "X major tick": {
                                "type": "float",
                                "default": 1200,
                                "key": "X_major_t",
                            },
                            "X minor tick": {
                                "type": "float",
                                "default": 300,
                                "key": "X_minor_t",
                            },
                            "X grid": {
                                "type": "bool",
                                "default": True,
                                "key": "X_grid",
                            },
                        },
                    },
                    "Y axis": {
                        "type": "group",
                        "children": {
                            "Y axis title": {
                                "type": "str",
                                "default": "Temperature",
                                "key": "Y_title",
                            },
                            "Y axis unit": {
                                "type": "str",
                                "default": "°C",
                                "key": "Y_unit",
                            },
                            "Y major tick": {
                                "type": "float",
                                "default": 10,
                                "key": "Y_major_t",
                            },
                            "Y minor tick": {
                                "type": "float",
                                "default": 2,
                                "key": "Y_minor_t",
                            },
                            "Y grid": {
                                "type": "bool",
                                "default": True,
                                "key": "Y_grid",
                            },
                        },
                    },

                    "Appearance": {
                        "type": "group",
                        "children": {
                            "Graph Background color": {
                                "type": "color",
                                "default": "#FFFFFF",
                                "key": "background_color",
                            },
                            "Dark mode": {
                                "type": "bool",
                                "default": False,
                                "key": "dark_mode",
                            },
                        },
                    },
                }
    print(generate_opts_dict(PARAMETER_SCHEMA))