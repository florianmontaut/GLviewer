from model.analysis.thermal import ThermalModelAnalysis
from model.analysis.fft import FFTAnalysis
from model.analysis.diff_external import DiffSignalAnalysis
from ressources.custom_types import qSignalType

class AnalysisFactory:
    REGISTRY = {
                qSignalType.MODEL       : ThermalModelAnalysis,
                qSignalType.FFT         : FFTAnalysis,
                qSignalType.DIFF_EXT    : DiffSignalAnalysis
                }

    def create(self, data):
        atype = qSignalType[data["type"]]
        params = data.get("params", {})
        
        if atype not in self.REGISTRY:
            raise ValueError(f"Unknown analysis type: {atype}")
        
        return self.REGISTRY[atype](**params)
    
    def analysis_from_dict(self,data):
        
        cls = self.REGISTRY[data['type']]
        return cls.from_dict(data)