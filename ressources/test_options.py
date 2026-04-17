
import sys
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton
)
from pyqtgraph.parametertree import Parameter, ParameterTree


# ============================================================
# 1) PARAMETER_SCHEMA (source de vérité)
# ============================================================

PARAMETER_SCHEMA = {
    "X axis": {
        "type": "group",
        "children": {
            "X title": {
                "type": "str",
                "default": "Time",
                "key": "X_title",
            },
            "X unit": {
                "type": "str",
                "default": "s",
                "key": "X_unit",
            },
            "X grid": {
                "type": "bool",
                "default": True,
                "key": "X_grid",
            },
        },
    },
    "Appearance": {
        "type": "group",
        "children": {
            "Background": {
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
    "Downsampling type":{
                        "type":"list",
                        "default": "peak",
                        "limits":
                            ["subsample","mean","peak"],
                        "key": "downsample_signals"},
    "Set working folder":{
                            "type":"file",
                            "default": "",
                            "enabled":True,
                            'fileMode':'Directory',
                            "key": "working_folder"
                        },
    'Search':           {
                            'type':'action',
                            "default": "",
                            "key": "search_action"
                        }
}


# ============================================================
# 2) generate_opts_dict
# ============================================================

def generate_opts_dict(schema: dict):
    """
    Génère automatiquement :
    (path tuple ou str) -> logical_key
    """
    opts_dict = {}

    def recurse(node, path=()):
        for name, spec in node.items():
            current_path = path + (name,) if path else name

            if "key" in spec:
                opts_dict[current_path] = spec["key"]

            if spec.get("type") == "group":
                recurse(
                    spec.get("children", {}),
                    current_path if isinstance(current_path, tuple)
                    else (current_path,)
                )

    recurse(schema)
    return opts_dict


# ============================================================
# 3) build_parameter_group (récursif)
# ============================================================

def build_parameter_group(name, schema):
    children = []

    for pname, spec in  schema.items():
        ptype = spec["type"]
        #la valeur actuelle sauvegardée dans le filter node est récupérée içi
        # -----------------------------
        # Signal selector (ComboBox)
        # -----------------------------
        # ---------- GROUP ----------
        
        if ptype == "group":
                group = build_parameter_group(
                                                    name=pname,
                                                    schema=spec.get("children", {}),
                                                    )
                group.setOpts(
                                expanded=spec.get("expanded", False)
                            )
                children.append(group)
                continue
        '''
        # ---------- ACTION ----------
        if ptype == "action":
            children.append(
                            Parameter.create(
                                            name=pname,
                                            type="action"
                                            )   
                            )
            continue
        
        # ---------- PEN ----------
        if ptype == "pen":
            # Tu peux plus tard éclater en sous-paramètres
            pen=Parameter.create(
                                name=pname,
                                type="pen"
                                )
            pen.setOpts(
                        expanded=spec.get("expanded", False)
                    )
            
            children.append(group)
            continue
        if ptype == "color":
            # Tu peux plus tard éclater en sous-paramètres
            color=Parameter.create(
                                name=pname,
                                type="color"
                                )
            color.setOpts(
                        expanded=spec.get("expanded", False)
                    )
            
            children.append(color)
            continue'''

        # ---------- SIMPLE TYPES ----------
        print(pname,ptype)
        param = {
                    "name": pname,
                    "type": ptype,
                    "value": spec.get("default",None),
                    "default": spec.get("default",None),
                    "limits": spec.get("limits",None),
                    "suffix": spec.get("suffix",None),
                    "enabled": spec.get("editable", True),
                    "tip": spec.get("description",None),
                }

        # Nettoyage
        print(param)
        param = {k: v for k, v in param.items() if v is not None}
        print(param)
        children.append(Parameter.create(**param))

    return Parameter.create(
                            name=name,
                            type="group",
                            children=children
                            )

# ============================================================
# 4) build_parameter_tree_for_object
# ============================================================

def build_parameter_tree_for_object(schema):
    return build_parameter_group("Graph settings", schema)


# ============================================================
# 5) updateOptions (version debug)
# ============================================================

def updateOptions(param_root, opts_dict):
    """
    Parcourt le ParameterTree et affiche (key, value)
    """
    print("\n--- updateOptions() ---")

    def recurse(param, path=()):
        for child in param.children():
            new_path = path + (child.name(),)

            if child.hasChildren():
                recurse(child, new_path)
            else:
                path_key = new_path if len(new_path) > 1 else new_path[0]
                if path_key in opts_dict:
                    logical_key = opts_dict[path_key]
                    print(f"{logical_key} = {child.value()}")

    recurse(param_root)


# ============================================================
# 6) Application de test
# ============================================================

class DebugWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ParameterTree Debug")

        layout = QVBoxLayout(self)

        # ParameterTree
        self.tree = ParameterTree()
        self.params = build_parameter_tree_for_object(PARAMETER_SCHEMA)
        self.tree.setParameters(self.params, showTop=False)

        layout.addWidget(self.tree)

        # Boutons
        self.btn_print_dict = QPushButton("Print opts_dict")
        self.btn_print_values = QPushButton("Print parameter values")

        layout.addWidget(self.btn_print_dict)
        layout.addWidget(self.btn_print_values)

        # opts_dict généré automatiquement
        self.opts_dict = generate_opts_dict(PARAMETER_SCHEMA)

        # connexions
        self.btn_print_dict.clicked.connect(self.print_opts_dict)
        self.btn_print_values.clicked.connect(self.print_values)

    def print_opts_dict(self):
        print("\n--- opts_dict ---")
        for k, v in self.opts_dict.items():
            print(f"{k} -> {v}")

    def print_values(self):
        updateOptions(self.params, self.opts_dict)


# ============================================================
# 7) Main
# ============================================================

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = DebugWindow()
    win.resize(500, 600)
    win.show()
    sys.exit(app.exec())
