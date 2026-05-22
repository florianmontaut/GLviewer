
from PyQt6 import QtCore

class AnalysisWorker(QtCore.QObject):

    finished = QtCore.pyqtSignal(object, object, object)  
    # signal, analysis, result

    error = QtCore.pyqtSignal(object, Exception)

    def __init__(self, signal_obj, analysis):
        super().__init__()
        self.signal = signal_obj
        self.analysis = analysis

    def run(self):
        try:
            result = self.analysis.compute(self.signal)
            self.finished.emit(self.signal, self.analysis, result)
        except Exception as e:
            self.error.emit(self.analysis, e)
