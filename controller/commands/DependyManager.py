
class DependencyManager:

    def __init__(self):
        self._cache = {}
        self._versions = {}

    def get_result(self, signal, analysis):

        key = (id(signal), id(analysis))
        current_version = signal.pipeline_version

        if key in self._cache and self._versions[key] == current_version:
            return self._cache[key]

        result = analysis.compute(signal)

        self._cache[key] = result
        self._versions[key] = current_version

        return result

    def invalidate_signal(self, signal):
        keys = [k for k in self._cache if k[0] == id(signal)]
        for k in keys:
            del self._cache[k]
            del self._versions[k]
