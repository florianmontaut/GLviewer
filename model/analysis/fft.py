
import numpy as np
import pyqtgraph as pg
from .base_analysis import AnalysisNode
from ressources.custom_types import qSignalType
from model.base_objects import DerivedSignalObject
from model.missing_data import fill_gaps
from ressources.custom_exceptions import AnalysisError


class FFTAnalysis(AnalysisNode):
    """Analyse FFT : transforme le signal en domaine fréquentiel."""

    action_type = qSignalType.FFT
    # part maximale de données manquantes (NaN), comblées par interpolation
    MAX_MISSING = 0.1
    PARAMETER_SCHEMA = {
        "Window": {
            "type": "list",
            "default": "hann",
            "values": ["none", "hann", "hamming"],
            "readonly": False,
            "key": "window",
        },
    }

    def validate(self, params):
        pass  # Pas de validation spécifique

    @property
    def display_name(self) -> str:
        return f"FFT ({self.get_param('window')})"

    def compute(self, parent_signal):
        x = parent_signal.x
        # données manquantes : quelques trous sont comblés par interpolation, au-delà de
        # MAX_MISSING le spectre serait celui de l'interpolation plutôt que de la mesure
        y, missing = fill_gaps(x, parent_signal.y)
        if missing.mean() > self.MAX_MISSING:
            raise AnalysisError(f"FFT impossible : {missing.mean():.0%} de données "
                                f"manquantes (maximum {self.MAX_MISSING:.0%})")
        fs = 1 / (x[1] - x[0])  # Fréquence d'échantillonnage

        # Applique la fenêtre
        if self.get_param('window') == 'hann':
            window = np.hanning(len(y))
        elif self.get_param('window') == 'hamming':
            window = np.hamming(len(y))
        else:
            window = np.ones(len(y))
        y_windowed = y * window

        # FFT
        fft = np.fft.fft(y_windowed)
        freq = np.fft.fftfreq(len(y), 1/fs)
        magnitude = np.abs(fft)[:len(freq)//2]  # Moitié positive
        freq_pos = freq[:len(freq)//2]

        # Crée un DerivedSignalObject pour le spectre
        derived_name = f"{parent_signal.name}_fft"
        pen = pg.mkPen(color="green")
        derived_signal = DerivedSignalObject(
            parent_signal=parent_signal,
            name=derived_name,
            x=freq_pos,
            y=magnitude,
            pen=pen,
            metadata={"fs": fs, "window": self.get_param('window'), "analysis_id": self.id}
        )
        return derived_signal