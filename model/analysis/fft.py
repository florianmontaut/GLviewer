
import numpy as np
import pyqtgraph as pg
from .base_analysis import AnalysisNode
from ressources.custom_types import qSignalType
from model.base_objects import DerivedSignalObject


class FFTAnalysis(AnalysisNode):
    """Analyse FFT : transforme le signal en domaine fréquentiel."""

    action_type = qSignalType.FFT
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
        y = parent_signal.y
        fs = 1 / (parent_signal.x[1] - parent_signal.x[0])  # Fréquence d'échantillonnage

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