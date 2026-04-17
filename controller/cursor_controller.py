
# controller/cursor_controller.py

import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal

class CursorController(QObject):
    """
    Gère un curseur libre ou magnétique.
    """

    cursor_moved = pyqtSignal(object)  # x, y

    def __init__(self):
        super().__init__()
        self.signal = None
        self.snap_enabled = False

    def set_signal(self, signal_obj):
        self.signal = signal_obj

    def set_snap(self, enabled: bool):
        self.snap_enabled = enabled

    def load_model(self,model):
        
        self.model=model

    def update_x(self, x: float):
        """
        Appelé lorsque le curseur X bouge.
        """
        if self.signal is None or not self.snap_enabled:
            self.cursor_moved.emit(x)
            return

        xs = self.signal.x
        ys = self.signal.y
        
        if len(xs) == 0:
            self.cursor_moved.emit(x)
            return

        #idx = np.searchsorted(xs, x)
        idx = np.argmin(np.abs(xs - np.ones(len(xs))*x))
        if idx <= 0:
            y = ys[0]
        elif idx >= len(ys):
            y = ys[-1]
        else:
            y = ys[idx]

        self.cursor_moved.emit([x,  float(y)])
