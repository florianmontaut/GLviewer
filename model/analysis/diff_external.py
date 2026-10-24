
import uuid
import numpy as np
import pyqtgraph as pg
from scipy.interpolate import interp1d

from .base_analysis import AnalysisNode
from ..base_objects import SignalObject,DerivedSignalObject
from ressources import custom_types
class DiffSignalAnalysis(AnalysisNode):


    action_type = custom_types.qSignalType.DIFF_EXT
    PARAMETER_SCHEMA = {
                        "Reference signal": {
                                    "type": "signal",
                                    "default": None,
                                    "readonly": False,
                                    "description": "Reference signal for difference",
                                    "key":"reference"
                                    },
                        'Interpolation':{
                                            'type':'list',
                                            'default': 'linear',
                                            'values':[  'linear','nearest','zero','nearest-up',
                                                        'slinear','quadratic','cubic', 'previous',
                                                        'next'],
                                            'key':'interp'
                                        },
                        'Signals alignement':{
                                            'type':'list',
                                            'default': 'start',
                                            'values':['start','stop'],
                                            'key':'time_alignment'
                                        },
                        }

    def validate(self,params):

        self._params['reference_file'] = None
        # self.id est attribué par AnalysisNode.__init__ (clé dans signal.analyses)

        if isinstance(params['reference'], SignalObject):
            self._params['reference_file'] = params['reference'].file.name
        elif  isinstance(params['reference'], str):
            self._reference_name = params['reference']
        else:
            raise ValueError('A reference signal must be a selected or a signal name passed')

    def get_params(self):
        super_params = super().get_params()
        if isinstance(self.get_param('reference'), SignalObject):
            super_params.update({'reference': self.get_param('reference').name})
        else:
            super_params.update({'reference': self.get_param('reference')})
        return super_params

    @property
    def display_name(self) -> str:
        #voir méthode ci-dessus, ne pas remplacer par  get_param !!
        return f"Diff ({self.get_params()['reference']})"

    def input_key(self, parent_signal) -> tuple:
        # la différence est aussi périmée quand le signal de référence change
        ref = self.get_param("reference")
        ref_key = (ref.input_key(), ref.file.removed) if isinstance(ref, SignalObject) else None
        return (parent_signal.input_key(), ref_key)

    def resolve_reference(self, signal_map: dict):
        if  ( not isinstance(  self.get_param('reference'), SignalObject)
                and hasattr(self,'_reference_name')):

            self.set_param('reference', signal_map.get(self._reference_name))
            if self.get_param('reference') is None:
                raise ValueError(
                    f"Reference signal '{self._reference_name}' not found"
                )

    #TODO: faire l'ensemble des méthodes d'alignement de interpolation
    def compute(self, parent_signal: SignalObject) -> DerivedSignalObject:

        ref_signal = self.get_param("reference")
        self._params['reference_file'] = ref_signal.file.name if ref_signal else None
        if ref_signal is None:
            raise RuntimeError("Reference signal not resolved")
        if ref_signal.file.removed:
            raise RuntimeError(f"le fichier de la référence ({ref_signal.file.name}) a été retiré")

        # Récupération des données calculées
        t_a, y_a = parent_signal.x, parent_signal.y
        t_b, y_b = ref_signal.x, ref_signal.y

        # Alignement temporel
        t_common = self._build_common_timebase(t_a, t_b)

        # Interpolation
        y_a_i = self._interpolate_signal(t_a, y_a, t_common)
        y_b_i = self._interpolate_signal(t_b, y_b, t_common)

        y_diff = y_a_i - y_b_i

        name = f"{parent_signal.name} - {ref_signal.name}"

        #! pas d'id contrairement à thermal
        return DerivedSignalObject(
            parent_signal=parent_signal,
            name=name,
            x=t_common,
            y=y_diff,
            pen=pg.mkPen("cyan", width=2),
            metadata={
                "type": "diff",
                "source": parent_signal.name,
                "reference": ref_signal.name,
                "interp": self.get_param("interp"),
                "alignment": self.get_param("time_alignment"),
                "analysis_id": self.id,
            },
        )


    def _build_common_timebase(self, t_a, t_b):

        align = self.get_param("time_alignment")

        if align == "start":
            t0 = max(t_a[0], t_b[0])
            t1 = min(t_a[-1], t_b[-1])
        elif align == "stop":
            duration = min(t_a[-1] - t_a[0], t_b[-1] - t_b[0])
            t1 = min(t_a[-1], t_b[-1])
            t0 = t1 - duration
        else:
            raise ValueError(f"Unknown alignment strategy: {align}")

        if t1 <= t0:
            raise RuntimeError("No overlapping time range between signals")

        # Pas de temps cible = plus fin des deux
        dt_a = np.median(np.diff(t_a))
        dt_b = np.median(np.diff(t_b))
        dt = min(dt_a, dt_b)

        return np.arange(t0, t1, dt)


    def _interpolate_signal(self, t_src, y_src, t_target):

        interp_type = self.get_param("interp")

        f = interp1d(
                        t_src,
                        y_src,
                        kind=interp_type,
                        bounds_error=False,
                        fill_value="extrapolate",
                    )

        return f(t_target)
