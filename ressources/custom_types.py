from enum import Enum,auto

class itemType(Enum):
    
    ROOT    = auto()
    FILE    = auto()
    RAW     = auto()
    FILTER  = auto()
    ANALYSE = auto()
    DERIVED = auto()
    CHANNEL = auto()    # voie logique de la vue « Par voie » (model.channels.ChannelGroup)
    CHANNEL_GROUP = auto()  # groupe de voies logiques créé par l'utilisateur (UserGroup)
class qSignalType(Enum):

    LOAD        = auto()
    FILTER      = auto()
    REF         = auto()
    DIFF        = auto()
    DIFF_EXT    = auto()
    AVG         = auto()
    RMS         = auto()
    OFFSET      = auto()
    OFFSET_X    = auto()
    MODEL       = auto()
    FFT         = auto()
    FORMULA     = auto()    # voie calculée par une formule (model.computed)
    ALIGN       = auto()    # recalage d'un fichier dans le temps (alignment_controller)
    DEL         = auto()
    SELECT      = auto()
    CHECK       = auto()
    OPTIONS     = auto()
    ISOLATE     = auto()
    TEXT        = auto()
    MACRO       = auto()
    START       = auto()
    STOP        = auto()
    
class ActionModifier(Enum):
    
    ADD_ACTION      = auto()
    REMOVE_ACTION   = auto()
    MODIFY_ACTION   = auto()

class fileType(Enum):

    GL      = auto()
    TXT     = auto()
    CSV     = auto()
    VCD     = auto()
    JSON    = auto()


class cursorType(Enum):

    WAVEFORM    = auto()
    H_BARS      = auto()
    V_BARS      = auto()
    VH_BARS     = auto()

class modelType(Enum):

    POLY            = auto()
    EXP             = auto()
    FIRST_ORDER     = auto()
    SECOND_ORDER    = auto()


class degree(Enum):

    FARENHEIT   = auto()
    CELSIUS     = auto()

class ImportMode(Enum):

    RESTORE     = auto()
    INTERACTIVE = auto()