
# model/filters/filter_factory.py

from model.filters.lowpass import LowPassFilter
from model.filters.offset import OffsetFilter
from model.filters.moving_average import MovingAverageFilter
from model.filters.diff import DiffFilter
from model.filters.time_shift import TimeShiftFilter

from ressources.custom_types import qSignalType

class FilterFactory:
    
    REGISTRY = {
        qSignalType.FILTER      : LowPassFilter,
        qSignalType.DIFF        : DiffFilter,
        qSignalType.AVG         : MovingAverageFilter,
        qSignalType.OFFSET      : OffsetFilter,
        qSignalType.OFFSET_X    : TimeShiftFilter,
        }

    def create(self, data):
        ftype = qSignalType[data["type"]]
        params = data.get("params", {})

        if ftype not in self.REGISTRY:
            raise ValueError(f"Unknown filter type: {ftype}")
        
        return self.REGISTRY[ftype](**params)

    def filter_from_dict(self,data):
        cls = self.REGISTRY[data["type"]]
        return cls.from_dict(data)


