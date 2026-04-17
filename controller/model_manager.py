from model.base_objects import SignalObject,DerivedSignalObject
from model.analysis.thermal import ThermalModelAnalysis 


class ModelManager:

    def __init__(self, signal: SignalObject):
        self.signal = signal
        self.analyses: list[ThermalModelAnalysis] = []
        self.derived_signals: dict[str, DerivedSignalObject] = {}
        self.active_analysis_id: str | None = None



    def create_thermal_model(
                            self,
                            label: str,
                            t_start: float,
                            t_end: float,
                            power: float
                        ) -> str:

        analysis = ThermalModelAnalysis(label=label)
        analysis.set_fit_range(t_start, t_end)
        analysis.run(self.signal.x, self.signal.y, power)

        derived_signal = analysis.create_derived_signal(self.signal)

        self.analyses.append(analysis)
        self.derived_signals[analysis.id] = derived_signal
        self.active_analysis_id = analysis.id

        self.signal.analyses.append(analysis)
        self.signal.derived_signals.append(derived_signal)

        return analysis.id



class ModelManager:

    def compute_analysis(self, signal, analysis):
        derived = analysis.compute(signal)
        signal.analyses.append(analysis)
        signal.derived_signals.append(derived)
        return derived

