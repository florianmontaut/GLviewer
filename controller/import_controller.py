import pandas as pd
import numpy as np
import csv,json,re,datetime
from collections import namedtuple

from PyQt6 import QtGui,QtCore,QtWidgets
from ressources import (custom_functions,custom_items,custom_types,
                        custom_dialogs,custom_exceptions)
from model.base_objects import Workspace,FileObject
from model.annotations import TextAnnotation
from model import txt_import
from model.filters.filter_factory import FilterFactory
from model.analysis.analysis_factory import AnalysisFactory

class ImportController(QtCore.QObject):


    file_signal = QtCore.pyqtSignal(FileObject)
    project_signal = QtCore.pyqtSignal(Workspace)

    def __init__(self,view: QtWidgets.QMainWindow,**opts):

        super().__init__()
        self.view = view
        self._from_project = custom_types.ImportMode.INTERACTIVE
        self.load_dict = {
                            custom_types.fileType.GL:
                            custom_items.ImportRequest(
                                                    file_format=custom_types.fileType.GL,
                                                    loader_label=(  "Loading GL files",
                                                                    "csv Files (*.csv)"),
                                                    loader= self.openGLCsvFiles
                                                    ) ,
                            custom_types.fileType.TXT:
                            custom_items.ImportRequest(
                                                    file_format=custom_types.fileType.TXT,
                                                    loader_label=("Loading .txt files",
                                                                "txt Files (*.txt);;csv Files (*.csv)"),
                                                    loader= self.openTxt
                                                    ),
                            custom_types.fileType.CSV:
                            custom_items.ImportRequest(
                                                    file_format=custom_types.fileType.CSV,
                                                    loader_label=("Loading .csv files",
                                                                "csv Files (*.csv)"),
                                                    loader= self.openCsvFiles
                                                    ),
                            custom_types.fileType.JSON:
                            custom_items.ImportRequest(
                                                    file_format=custom_types.fileType.JSON,
                                                    loader_label=("Loading .json project files",
                                                                "json Files (*.json)"),
                                                    loader= self.openProject
                                                    )
                        }
        self.file_caracs = {
                            'sampling':"Sampling",
                            'n_samples':'Total data points',
                            'recordDate':'Trigger time',
                            'CH':'CH',
                            'data':'Data'
                            }
        self.txt_import_settings={}
        default_time = datetime.datetime.now()

        self.opts={
        "remove_old_graph"          : False,
        "remove_overrange"          : True,
        "auto_filter"               : False,
        "datetime_active"           : False,
        "downsample_signals"        : False,
        "downsample_ratio"          : 10,
        "downsample_type"           : "Peak",
        "downsample_thres"          : 10,
        "default_sampling_txt"      : 20*10**-3,
        "default_sampling_csv"      : 1,
        "default_time"              : default_time,
        "custom_folder"             :  "",
        "latest_import"             : True,
        "default_delimitor"         : ";",
        "default_unit_separator"    : ","
        }

        if opts:
            self.updateOptions(**opts)

    @property
    def defaultAdress(self):
        if self.opts['latest_import']:
            return self.view.latest_dir
        else:
            if self.opts['custom_folder']:
                return self.opts['custom_folder']
            else:
                return self.view.default_dir

    def updateOptions(self,opts):

        self.opts.update(opts)

    def openGLCsvFiles(self,fname,settings=None):
        """
        Méthode permettant de charger des fichiers .CSV de type GLviewer dans l'appli
        Arguments:
                fnames   --
        Returns:
                None     --
        """

        with open(fname, 'r') as csvfile:

            #configuration du 'sniffer' csv permettant de déterminer le type de délimiteur ;/,
            dialect = csv.Sniffer().sniff(csvfile.read(4096), delimiters=';,')
            csvfile.seek(0)#utilisation du sniffer
            rawtxt = list(csv.reader(csvfile, dialect))
            file_caracs={}
            file_caracs.update(self.file_caracs)
            # listes des phrases clées par ordre d'apparition dans un fichier csv classique

            # création du générateur n permettant de simplifier la boucle for de recherche
            key_gen=(attribut for attribut in file_caracs.values())
            #index des caractéristiques du fichier
            id_caracs = {key : None for key in file_caracs.keys()}
            #la première phrase recherchée 'Sampling'est chargée dans a
            attribut=next(key_gen)

            #la boucle qui suit relève les numéros des lignes contenants les éléments
            #recherchés:
            for index,element in enumerate(rawtxt):
                if index >=100 :
                    break
                try:
                    # les lignes vides de l'en-tête sont ignorées
                    if element and element[0] == attribut:
                        key=[key for key,val in file_caracs.items() if val == attribut][0]
                        id_caracs[key] = index
                        attribut = next(key_gen)#on charge la nouvelle phrase recherchée
                except StopIteration as e:
                    if not any(id_caracs.values()):
                        raise custom_exceptions.GLStructureError(
                                                "le fichier .csv n'est pas au format"+
                                                " GL820/840. L'un des 5 paramètres"+
                                                " qui suit n'a pas été trouvé:"+
                                                " Sampling/Total data points/"+
                                                "Trigger time/CH/Data"
                                                ) from e
                    break

            check_table=[]
            #channels sera une liste de channel_settings
            channels=[]

            for key,val in file_caracs.items():

                if val=='Sampling':
                    file_caracs[key] = custom_functions.mysplit(rawtxt[id_caracs[key]][1])
                elif val=='Total data points':
                    file_caracs[key] = int(rawtxt[id_caracs[key]][1])
                elif val=='Trigger time':
                    file_caracs[key] = self.convertDate(rawtxt[id_caracs[key]][1:3])
                elif val=='CH':
                    channels_settings_list=rawtxt[id_caracs[key]]
                    name_position = [i for i, j in enumerate(channels_settings_list)
                                            if j.strip(' ') == 'Signal name'][0]
                    #contruction du span: max,min,unit
                    span_position = [(i,i+1,i+2) for i, j in enumerate(channels_settings_list)
                                            if j.strip(' ') == 'Span'][0]
                    type_position = [(i,i+1) for i, j in enumerate(channels_settings_list)
                                            if j.strip(' ') == 'Input'][0]

                    for n in range(id_caracs[key]+1,id_caracs["data"]):
                        line=rawtxt[n]
                        #ajout d'un test sur la présence des caractères "CH" afin d'éliminer
                        #les risques de mauvais tronçonnages du aux différentes version de GL
                        if "CH" in line[0]:
                            name=line[name_position]
                            #print ("import l 120",rawtxt[n][5])
                            # le signe est conservé (span négatif : ex. -50 °C)
                            span_max=float(re.sub(r'[^0-9.\-]', '',
                                            line[span_position[0]].replace(',','.')))
                            span_min=float(re.sub(r'[^0-9.\-]', '',
                                            line[span_position[1]].replace(',','.')))
                            unit=line[span_position[2]]
                            #! il faudrait remonter l'ensemble de ces données au workspace !
                            #! l'unité, le min max de l'échelle et le disabled qui pourrait
                            #! remplacer ou s'intégrer dans le valid_table
                            channels.append({
                                                'channel'   : line[0].strip(),
                                                'name'      : name,
                                                'min'       : span_min,
                                                'max'       : span_max,
                                                'unit'      : unit,
                                                'disabled'  : False,
                                            })
                    channels_names=[]
                    for num,channel_setting in enumerate(channels):
                        #Deepcopy de channels sans quoi filtre est un pointeur de channels
                        filtre=[setting['name'] for setting in channels]
                        name=channel_setting['name']
                        a=filtre.pop(num)
                        #si le nom est déjà présent dans la liste on ajoute CH num pour le
                        #différencier.
                        if name in filtre:
                            channels[num]['name']=f'CH{num} {name}'
                        # nom éventuellement rendu unique (sinon colonnes en double)
                        channels_names.append(channels[num]['name'])

                    #pour éviter la pluspart des problématiques du à l'introduction d'espaces
                    #retour à la ligne on cherche chacun des éléments et leur index plutôt
                    #que d'imposer un index fixe (il existe de multiple template des extracts
                    # GLviewer, selon la version du firmware, software ou du GL en lui-même)
                    id_data_row=id_caracs['data']+1
                    start_flag=None
                    data_columns=None
                    for n,line in enumerate(rawtxt[id_data_row:id_data_row+20]):
                        if (line[0] in ['No.','NO.','Number']) and data_columns is None:
                            data_columns=[i for i, j in enumerate(line)
                                                    if j.strip(' ').startswith("CH") == True]
                            first_column_id=data_columns[0]
                            #attention aux slices! Exemple a=[0,1,5,6,9,7] print(a[1:3]) => [1,5,6]
                            last_column_id=data_columns[-1]+1
                        try:
                            if int(line[0])==1 or int(line[0])==2:
                                if start_flag==True:
                                    first_data_row=id_data_row+n-1
                                    break
                                start_flag=True
                        except:
                            continue

                    if dialect.delimiter==';':
                        data=[]
                        for donnees in rawtxt[first_data_row:]:
                            data.append([element.replace(',','.')
                                        for element in donnees[first_column_id:last_column_id]])
                        #passage des datas de string à float
                        df=pd.DataFrame(data,columns=channels_names)
                    else:
                        #Création du dataframe dans File_caracs[3], en prenant les données
                        #des colonnes 3 à la dernière colonnes des voies de mesures, en prenant
                        #les noms des channels comme identifiant
                        df=pd.DataFrame([donnees[first_column_id:last_column_id]
                                        for donnees in rawtxt[first_data_row:]],
                                        columns=channels_names)

                    for col in df:
                        channels_span=[[setting['max'],setting['min']] for setting in channels
                                        if setting['name']==col][0]
                        #passage des datas de string à float
                        df[col]=pd.to_numeric(df[col],errors='coerce')
                        check_table.append(self.isChannelValid(df[col],
                                                            channels_span,
                                                            active=self.opts["remove_overrange"]))
                    #remplacement des 'burnout' et tout autre éléments qui n'est pas un float:
                    df=df.fillna(-20)
            #insertion d'une colonne Time en première position dans le dataframe
            df.insert(  loc=0,
                        column='Time',
                        value=np.linspace(  0,
                                            (file_caracs['n_samples']-1)*
                                            file_caracs['sampling'],
                                            file_caracs['n_samples']
                                        )
                        )
            #configuration de la colonne Time comme index du dataframe
            data=df.set_index('Time',append=True)
            file_struct=custom_items.FileStruct(
                                            address         = fname,
                                            file_type       = custom_types.fileType.GL.name,
                                            sampling        = file_caracs['sampling'],
                                            n_samples       = file_caracs['n_samples'],
                                            recordDate      = file_caracs['recordDate'],
                                            import_params   = {
                                                'check_table': check_table,
                                                # numéro de voie du GL par nom de voie
                                                'channel_ids': {setting['name']: setting['channel']
                                                                for setting in channels},
                                                },
                                            data            = data
                                            )
            if self._from_project == custom_types.ImportMode.INTERACTIVE:

                self.send_file_to_workspace(file_struct)
            else:
                return file_struct

    def _get_import_settings(self,params):
        self.txt_import_settings=params

    def ImportWizard(self,adress,params=None):

        if params is None:
            delim       = None
            unitDelim   = None
        else:
            delim       = params.get('delim',None)
            unitDelim   = params.get('unitdelim',None)
            
        if delim is None:
            delim = self.opts["default_delimitor"]
        if unitDelim is None:
            unitDelim = self.opts["default_unit_separator"]

        userInput = custom_dialogs.ImportWizardDialog(
                                                        adress=adress,
                                                        delimitor=delim,
                                                        unitDelim=unitDelim,
                                                        default_sampling=
                                                            self.opts["default_sampling_txt"]
                                                    )
        userInput.params_ready.connect(self._get_import_settings)

        result = userInput.exec()
        if result != QtWidgets.QDialog.DialogCode.Accepted:
            return None

        settings = self.txt_import_settings or userInput.collect_params()
        self.txt_import_settings = settings

        return self.openTxt(adress, settings)


    def ImportErrorUserWarning(self,errorStruct):

        #?revoir le principe de dictionnaire qui semble alambiqué
        format_dict=    {custom_types.fileType.GL:"Graphtec CSV file",
                        custom_types.fileType.JSON:"JSON file",
                        custom_types.fileType.TXT:"Plain Txt file",
                        custom_types.fileType.CSV:"Plain CSV file"}

        userInput = custom_dialogs.ImportErrorDialog(error = errorStruct[0],
                                                currentFormat = errorStruct[1],
                                                importFormats = format_dict)

        userInput.accepted.connect(lambda: self.loaderSelect(
                                                    (userInput.getFormat(),
                                                    [errorStruct[2]])
                                                    ))
        userInput.show()



    def openCsvFiles(self,fname,mode_etuve=False,settings=None):
        """
        Méthode permettant de charger un fichier .csv exporter par l'automate du CHILLER
        Arguments:
                None   --
        Returns:
                None   --
        """
        file_caracs=self.file_caracs
        with open(fname, 'r') as csvfile:

            dialect = csv.Sniffer().sniff(csvfile.read(4096), delimiters=';,\t')
            csvfile.seek(0)
            rawtxt      = list(csv.reader(csvfile, dialect))
            n_points    = len(rawtxt)-1
            sampling    = self.opts["default_sampling_csv"]
            start_time  = self.opts["default_time"]
            channels    =[]
            check_table =[]

            for val in rawtxt.pop(0):
                if val:
                    channels.append(val)
            channels.pop(0)
            #si le nombre de channels est égale au nombre de colonnes des data,
            #il faut alors retirer les colonnes X en doublon
            if (len(channels)+1)==len(rawtxt[1]):
                if channels[0]=="Temp_amb":
                    mode_etuve=True
                    channels=channels[0::1]
                else:
                    channels=channels[1::2]
                    mode_etuve=False
            if mode_etuve==True:
                data=[line[1::1] for line in rawtxt]
                #!écrase le sampling par défaut
                sampling=int(rawtxt[2][0])-int(rawtxt[1][0])
            else:
                data=[line[1::2] for line in rawtxt]
            df=pd.DataFrame(data,columns=channels)
            for signal in channels:
                df[signal]=pd.to_numeric(df[signal],errors='coerce')
                # TODO channels span: faut-il vérifier la validité des données sur un fichier csv?
                channels_span=1000
                check_table.append(self.isChannelValid(df[signal],
                                                            channels_span,
                                                            active=self.opts["remove_overrange"]))

            df.insert(loc=0,column='Time',value=np.linspace(0,(n_points-1)*sampling,n_points))
            data=df.set_index('Time',append=True)

            file_caracs=custom_items.FileStruct(
                                                address         = fname,
                                                file_type       = custom_types.fileType.CSV.name,
                                                sampling        = sampling,
                                                n_samples       = n_points,
                                                recordDate      = start_time,
                                                import_params   = {'check_table': check_table},
                                                data            = data
                                            )
            if self._from_project == custom_types.ImportMode.INTERACTIVE:
                self.send_file_to_workspace(file_caracs)
            else:
                return file_caracs

    def openTxt(self,fname,settings=None):
        """
        Méthode permettant de charger un fichier .txt (exemple enregistrement des NTCs via matis).
        Le découpage (model.txt_import.parse_txt) est le même que celui de l'aperçu de
        l'import wizard.
        Arguments:
                fname       --  adresse du fichier
                settings    --  réglages de l'import wizard (None : détection du séparateur,
                                noms des voies en première ligne)
        Returns:
                None   --
        """
        default_settings={
                    'delim'             : txt_import.DEFAULT_DELIMITERS,
                    'unitdelim'         : '.',
                    'start'             : 0,
                    'columns'           : [],
                    'sigNames'          : True,
                    'isFirstColIndex'   : False,
                }
        # premier chargement direct : découpage strict, en cas de doute le wizard s'ouvre
        strict = settings is None
        if settings is None:
            settings = default_settings

        try:
            result = txt_import.parse_txt(fname, settings, self.opts["default_sampling_txt"],
                                          strict=strict)
        except (custom_exceptions.TxtDelimiterError, custom_exceptions.TxtFormatError):
            raise
        except Exception as e:
            raise custom_exceptions.TxtDelimiterError(f"Failed to load TXT file {fname}"
                                                        ) from e

        df = result.data
        # pas de détection des voies HZ : les données d'un .txt (puissance, tension...)
        # n'ont pas de plage connue, elles sont toutes affichées
        data=df.set_index('Time',append=True)

        file_caracs=custom_items.FileStruct(
                                            address         = fname,
                                            file_type       = custom_types.fileType.TXT.name,
                                            sampling        = result.sampling,
                                            n_samples       = len(df),
                                            recordDate      = self.opts["default_time"],
                                            import_params   = settings,
                                            data            = data,
                                        )
        if self._from_project == custom_types.ImportMode.INTERACTIVE:
            self.send_file_to_workspace(file_caracs)
        else:
            return file_caracs

    def send_file_to_workspace(self,file_caracs:custom_items.FileStruct):

        # Création du modèle métier
        file_obj = FileObject(file_caracs)
        # Ajouter chaque colonne comme signal brut
        for col in file_obj.data.columns[:]:
            file_obj.add_signal(col)
        hidden = self.hide_invalid_channels(file_obj)
        if hidden:
            self.view.statusbar.showMessage(
                            f"{len(hidden)} voie(s) non exploitable(s) (HZ) masquée(s) : "
                            + ", ".join(hidden), 10000)
        self.file_signal.emit(file_obj)

    @staticmethod
    def hide_invalid_channels(file_obj:FileObject)->list[str]:
        """
        Décoche (comme le ferait l'utilisateur dans l'arborescence) les voies déclarées non
        exploitables à l'import (import_params['check_table'], voir isChannelValid).
        Uniquement au premier chargement d'un fichier : à la réouverture d'un projet, la
        visibilité sauvegardée (choix de l'utilisateur) est conservée.

        Returns:
            list[str]: noms des voies masquées
        """
        check_table=(file_obj.import_params or {}).get('check_table', [])
        if len(check_table) != len(file_obj.signals):
            return []
        hidden=[]
        for sig, valid in zip(file_obj.signals, check_table):
            if not valid:
                sig.visible=False
                hidden.append(sig.name)
        return hidden


    @staticmethod
    def isChannelValid(data,threshold,active,ratio=0.9,jump_ratio=0.1,max_jumps=0.05)->bool:
        """
        Méthode permettant de vérifier si les données du channel sont exploitables.
        Une voie est déclarée non exploitable (HZ : thermocouple sectionné, entrée du
        datalogger restée en l'air...) si :
            - moins de `ratio` (90 %) de ses points sont numériques et dans la plage
              [min, max] de la voie (ex: span du GL). Une entrée en l'air sature
              typiquement aux limites du capteur (-270 °C / +900 °C pour un TC K) ;
            - OU si elle est erratique : plus de `max_jumps` (5 %) des variations d'un
              point au suivant dépassent `jump_ratio` (10 %) de la largeur de la plage.
              Une température réelle varie lentement d'un échantillon au suivant, une
              entrée en l'air saute en permanence, même quand elle reste dans la plage.
        Arguments:
                data        {pandas.series} signal
                threshold   {tuple(float,float)|float} seuils à partir des quels les données
                                                sont considérées comme erronées, dans
                                                n'importe quel ordre. Une valeur seule
                                                donne la plage symétrique [-val, val]
                active       {bool}         l'option de filtrage des signaux est elle active
                ratio       {float}         part minimale des points devant être dans la plage
                jump_ratio  {float}         saut (en part de la largeur de la plage) à partir
                                            duquel une variation est jugée anormale
                max_jumps   {float}         part maximale de variations anormales
        Returns:
                {bool}                      resultat du channel est-il valide ?
        """
        if not active:
            return True
        if ratio<0 or ratio>1 :
            raise ValueError
        if np.isscalar(threshold):
            threshold=(-abs(threshold),abs(threshold))
        #les loaders GL/TXT passent (max,min)
        low,high=min(threshold),max(threshold)

        values=pd.to_numeric(pd.Series(data),errors='coerce').to_numpy(dtype=float)
        if values.size == 0:
            return False
        # NaN (BURNOUT, texte...) : hors plage
        in_span=(values>=low) & (values<=high)
        if in_span.mean() < ratio:
            return False

        jumps=np.abs(np.diff(values))
        jumps=jumps[np.isfinite(jumps)]
        if jumps.size and high > low:
            if np.mean(jumps > jump_ratio*(high-low)) > max_jumps:
                return False
        return True

    @staticmethod
    def convertDate(date):

        date_str =' '.join(date)
        if '-'in date_str:
            date_format = '%d-%m-%Y %H:%M:%S'
            try:
                date_obj = datetime.datetime.strptime(date_str, date_format)
            except ValueError:
                date_format = '%Y-%m-%d %H:%M:%S'
                try:
                    date_obj = datetime.datetime.strptime(date_str, date_format)
                except ValueError:
                    return "Failed date conversionn with '-' separator"
        elif '/'in date_str:
            date_format = '%d/%m/%Y %H:%M:%S'
            try:
                date_obj = datetime.datetime.strptime(date_str, date_format)
            except ValueError:
                date_format = '%Y/%m/%d %H:%M:%S'
                try:
                    date_obj = datetime.datetime.strptime(date_str, date_format)
                except ValueError:
                    return "Failed date conversionn with '-' separator"
        else:
            return None

        return date_obj
        #On remplace "Trigger time" par sa valeur. "Start time" ne correspond
        #pas au début de l'enregistrement

    def openProject(self,fname,settings=None):

        self._from_project=custom_types.ImportMode.RESTORE
        with open(fname, "r", encoding="utf-8") as f:
            data = json.load(f)

        ws = Workspace()
        for file_data in data["workspace"]["files"]:
            file_type=custom_types.fileType[file_data['file_type']]
            while True:
                try:
                    import_request:custom_items.ImportRequest = self.load_dict[file_type]
                    #settings par mot-clé : le 2e argument positionnel d'openCsvFiles
                    #est mode_etuve
                    file_caracs=import_request.loader(  fname=file_data['address'],
                                                        settings=file_data['import_params'])
                    break
                except custom_exceptions.TxtDelimiterError  as e:
                    QtWidgets.QMessageBox.warning(self.view,
                                        "Séparateur des colonnes invalide",
                                        str(e)+
                                        '\n Veuillez vérifier le type de séparaterur utilisé.')
                    file_caracs = self.ImportWizard(file_data['address'])
                    if file_caracs is None:
                        raise custom_exceptions.TxtFormatError(
                            f"Import cancelled for {file_data['address']}"
                        )
                    break
                except custom_exceptions.TxtFormatError  as e:
                    QtWidgets.QMessageBox.warning(self.view,
                                        "Format invalide",
                                        str(e)+'\n Veuillez vérifier le format du fichier.')
                    file_caracs = self.ImportWizard(file_data['address'])
                    if file_caracs is None:
                        raise custom_exceptions.TxtFormatError(
                            f"Import cancelled for {file_data['address']}"
                        )
                    break

            file_obj = FileObject(file_caracs)
            # paramètres du fichier (absents des projets plus anciens)
            file_obj.set_params({key: file_data[key]
                                 for key in ('offset','start_x','stop_x','label')
                                 if file_data.get(key) is not None})
            file_obj.signals_from_dict(file_data, FilterFactory(),AnalysisFactory())
            ws.add_file(file_obj)

        # textes du graphique (absents des projets plus anciens)
        for annotation_data in data["workspace"].get("annotations", []):
            annotation = TextAnnotation.from_dict(annotation_data)
            ws.annotations[annotation.id] = annotation
        # appariement des voies de la vue « Par voie »
        ws.channels_from_dict(data["workspace"].get("channels"))
        ws.path = fname

        self._from_project=custom_types.ImportMode.INTERACTIVE
        self.project_signal.emit(ws)


    def loaderSelect(self,loadStruct:dict):
        """
        Méthode gérant la réception des données du viewer. Cette dernière utilise la méthode
        liée à l'extension du(es) fichier(s) à charger. Seul plusieurs fichiers du même type
        (GL/CSV/TXT) peuvent être chargés par la méthode loaderSelect.

        Arguments:
                fname      --
                fileType   --
        Returns:
                None        --
        """

        fileType    =   custom_types.fileType[loadStruct["file_type"]]
        fname      =   loadStruct["address"]
        params      =   loadStruct["import_params"]

        try:
            import_request=self.load_dict[fileType]
            message,_ = import_request.loader_label
            self.view.statusbar.showMessage(message,3000)
            import_request.loader(fname=fname,settings=params)
        except custom_exceptions.TxtDelimiterError  as e:
            QtWidgets.QMessageBox.warning(self.view,
                                "Séparateur des colonnes invalide",
                                str(e)+'\n Veuillez vérifier le type de séparaterur utilisé.')
            self.ImportWizard(fname,params)
        except custom_exceptions.TxtFormatError  as e:
            QtWidgets.QMessageBox.warning(self.view,
                                "Format invalide",
                                str(e)+'\n Veuillez vérifier le format du fichier.')
            self.ImportWizard(fname,params)
        except custom_exceptions.CsvStructureError  as e:
            QtWidgets.QMessageBox.warning(self.view,
                                "Structure de donnée invalide",
                                str(e)+'\n Veuillez vérifier la structure du fichier CSV.')
            self.ImportWizard(fname,params)
        except custom_exceptions.GLStructureError  as e:
            QtWidgets.QMessageBox.warning(self.view,
                                "Structure de donnée invalide",
                                str(e)+'\n Veuillez vérifier la structure du fichier GL.')
            self.ImportWizard(fname,params)
        except Exception as err:
            errorStruct=[err,fileType,fname,params]
            self.ImportErrorUserWarning(errorStruct)


    def load_file_dialog(self,fileType:custom_types.fileType,adress=None):
        """
        Méthode gérant la fenêtre de dialogue permettant de charger des fichiers .CSV
        de type GLviewer dans l'appli.

        Arguments:
                adress      --
                fileType    --
        Returns:
                None        --
        """
        
        import_request : custom_items.ImportRequest = self.load_dict[fileType]

        message,file_extension = import_request.loader_label
        self.view.statusbar.showMessage(message,3000)
        fname,_ = QtWidgets.QFileDialog.getOpenFileName(  self.view,"Open file",
                                                                self.defaultAdress,
                                                                file_extension)
        if not fname:
            return

        if isinstance(fname,list):
            fname=fname[0]

        try:
            self.view.statusbar.showMessage(f"Loading file: {fname}",3000)
            import_request.loader(fname=fname)
        except Exception as e :
            print(e)
            self.ImportWizard(fname)