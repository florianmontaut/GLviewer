# tests/test_large_files.py
"""Performances sur les gros fichiers (ex: .txt de NTC, 1 million de lignes à 1 Hz)."""
import numpy as np
import pytest

from model import txt_import
from helpers import load


def test_preview_reads_only_the_beginning(tmp_path):
    """L'aperçu du wizard (max_rows) ne lit pas la suite du fichier : ici illisible."""
    path = tmp_path / "gros.txt"
    with open(path, "wb") as f:
        f.write(b"t;a\r\n" + b"".join(f"{i};{i}\r\n".encode() for i in range(100)))
        f.write(b"x" * 200000 + b"\r\n")           # ligne plus longue que la limite csv
    settings = {'delim': ';', 'unitdelim': '.', 'start': 0, 'columns': [],
                'sigNames': True, 'isFirstColIndex': True}

    result = txt_import.parse_txt(str(path), settings, 1.0, max_rows=50)
    assert len(result.data) == 50
    with pytest.raises(Exception):
        txt_import.parse_txt(str(path), settings, 1.0)      # lecture complète


def test_graph_clips_curves_to_view(ctrl):
    assert ctrl.graph_ctrl.plot.ctrl.clipToViewCheck.isChecked()


def test_time_axis_is_cached_and_read_only(ctrl, csv_files):
    file_obj = load(ctrl, csv_files[0])[0]
    sig_a, sig_b = file_obj.signals
    assert sig_a.x is sig_b.x                       # un seul axe des temps par fichier
    with pytest.raises(ValueError):
        sig_a.x[0] = 1.0

    file_obj.set_offset(100.0)
    np.testing.assert_allclose(sig_a.x[:2], [100.0, 101.0])


def test_raw_y_is_a_copy(ctrl, csv_files):
    sig = load(ctrl, csv_files[0])[0].signals[0]
    raw = sig.raw_y
    raw[0] = -999
    assert sig.raw_y[0] != -999
