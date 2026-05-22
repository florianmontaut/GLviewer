from controller.thread_controller import ThreadController
class DependencyManager:

    def __init__(self,thread_controller:ThreadController):
        self._cache = {}
        self._versions = {}
        self.thread_controller = thread_controller
        self.thread_controller.result_ready.connect(self._store_result)

    def get_result(self, signal, analysis):

        key = (id(signal), id(analysis))
        current_version = signal.pipeline_version

        if key in self._cache and self._versions[key] == current_version:
            return self._cache[key]

        # async launch
        self.thread_controller.compute(signal, analysis)
        return None  # pas encore prêt

    def _store_result(self, signal, analysis, result):

        key = (id(signal), id(analysis))

        self._cache[key] = result
        self._versions[key] = signal.pipeline_version

    def invalidate_signal(self, signal):
        keys = [k for k in self._cache if k[0] == id(signal)]
        for k in keys:
            del self._cache[k]
            del self._versions[k]
