
from PyQt6 import QtCore
from model.analysis.analysis_worker import AnalysisWorker

class ThreadController(QtCore.QObject):

    result_ready = QtCore.pyqtSignal(object, object, object)
    # signal, analysis, derived

    def __init__(self):
        super().__init__()
        self.threads = []

    def compute(self, signal, analysis):

        thread = QtCore.QThread()
        #! méthode .copy() et .clone() à implémenter
        #! ces méthodes fige les données en entrée de l'analyse afin de ne pas
        #! planter le calculs si l'utilisateur vient à modifier le signal source
        worker = AnalysisWorker(signal.copy(), analysis.clone())

        worker.moveToThread(thread)

        thread.started.connect(worker.run)

        worker.finished.connect(self._on_finished)
        worker.error.connect(self._on_error)

        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        thread.start()

        self.threads.append(thread)  # éviter GC

    def _on_finished(self, signal, analysis, result):
        self.result_ready.emit(signal, analysis, result)

    def _on_error(self, analysis, error):
        print(f"[Thread error] {analysis}: {error}")

