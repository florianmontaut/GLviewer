params={
    
    "Import settings": {
                        "type": "group",
                        "children": {

                            "Remove old viewer data when importing new file": {
                                                                        "type": "bool",
                                                                        "default": False,
                                                                        "key": "remove_old_graph",
                                                                        },

                            "Remove overrange channels": {
                                                            "type": "bool",
                                                            "default": True,
                                                            "key": "remove_overrange",
                                                        },

                            "Auto filter": {
                                            "type": "bool",
                                            "default": False,
                                            "key": "auto_filter",
                                        },

                            "Use the file datetime to synchronize log files": {
                                                                        "type": "bool",
                                                                        "default": False,
                                                                        "key": "datetime_active",
                                                                    },

                            # vue « Par voie » : voies regroupées par nom ou par numéro CH
                            "Channel matching between files": {
                                        "type": "list",
                                        "default": "Ask when a 2nd file is loaded",
                                        "limits": ["Ask when a 2nd file is loaded",
                                                   "By channel name",
                                                   "By channel number (CH)"],
                                        "key": "channel_matching",
                                    },

                            "Downsample at import": {
                                        "type": "group",
                                        "children": {
                                                    "Active": {
                                                        "type": "bool",
                                                        "default": True,
                                                        "key": "downsample_signals",
                                                    },
                                                    "Downsampling factor": {
                                                        "type": "int",
                                                        "default": 10,
                                                        "limits": [2, None],
                                                        "key": "downsample_ratio",
                                                    },
                                                    "Downsampling type": {
                                                        "type": "list",
                                                        "default": "peak",
                                                        "limits": ["subsample", "mean", "peak"],
                                                        "key": "downsample_type",
                                                    },
                                                    "Downsampling threshold": {
                                                        "type": "int",
                                                        "default": 10,
                                                        "limits": [2, None],
                                                        "key": "downsample_thres",
                                                    },
                                                },
                                            },

                            "File import setting": {
                                                    "type": "group",
                                                    "children": {

                                                        "Use latest files as working folder":
                                                            {
                                                            "type": "bool",
                                                            "default": True,
                                                            "key": "latest_import",
                                                            },

                                                        "Set working folder": {
                                                            "type": "file",
                                                            "default": "",
                                                            "fileMode": "Directory",
                                                            "key": "custom_folder",
                                                            },
                                                    },
                                                },
                        },
                    },

    "Export settings": {
                        "type": "group",
                        "children": {
                                    "Export raw channels": {
                                                            "type": "bool",
                                                            "default": True,
                                                            "key": "export_raw",
                                                            },
                                    "Export disabled channels": {
                                                                "type": "bool",
                                                                "default": True,
                                                                "key": "export_disabled",
                                                                },
                                    "Export modified channels": {
                                                                "type": "bool",
                                                                "default": True,
                                                                "key": "export_modified",
                                                                },
                                },
                        },

    
    "Filter settings": {
                        "type": "group",
                        "children": {
                                        "Default filter cut-off frequency": {
                                                            "type": "float",
                                                            "default": 0.003,
                                                            "limits": [1e-6, None],
                                                            "suffix": "Hz",
                                                            "key": "cutoff_frequency",
                                                            },
                                        "Default filter order": {
                                                            "type": "float",
                                                            "default": 3,
                                                            "limits": [1, 10],
                                                            "key": "filter_order",
                                                            },
                                    },
                        },

    "Graph settings": {
                        "type": "group",
                        "children": {
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
                                    "Update axis when signal selected": {
                                                                        "type": "bool",
                                                                        "default": True,
                                                                        "key": "update_selected",
                                                                        },
                                    "Downsample": {
                                                    "type": "group",
                                                    "children": {
                                                        "Active": {
                                                            "type": "bool",
                                                            "default": True,
                                                            "key": "downsample",
                                                        },
                                                        "Downsampling factor": {
                                                            "type": "int",
                                                            "default": 10,
                                                            "limits": [2, None],
                                                            "key": "downsample_ratio",
                                                        },
                                                        "Downsampling type": {
                                                            "type": "list",
                                                            "default": "peak",
                                                            "limits": [ "subsample",
                                                                        "mean",
                                                                        "peak"],
                                                            "key": "downsample_type",
                                                        },
                                                    },
                                    },
                                    # données manquantes (BURNOUT, cellule vide...) : les
                                    # calculs les excluent toujours, seul l'affichage change
                                    "Missing data": {
                                        "type": "group",
                                        "children": {
                                                    "Display": {
                                                        "type": "list",
                                                        "default": "Gap in the curve",
                                                        "limits": ["Gap in the curve",
                                                                   "Placeholder value"],
                                                        "key": "missing_display",
                                                    },
                                                    "Placeholder value": {
                                                        "type": "float",
                                                        "default": -20.0,
                                                        "key": "missing_value",
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
                                },
                        },
}

