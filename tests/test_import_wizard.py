# tests/test_import_wizard.py
"""Import des fichiers .txt : découpage commun (model.txt_import) et aperçu du wizard."""
import numpy as np
import pytest
import pyqtgraph as pg
from PyQt6 import QtCore

from model import txt_import
from ressources.custom_dialogs import ImportWizardDialog
from ressources.custom_exceptions import TxtDelimiterError, TxtFormatError


def _write(tmp_path, text, name="mesures.txt"):
    path = tmp_path / name
    path.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
    return str(path).replace("\\", "/")


N = 50


@pytest.fixture
def txt_file(tmp_path):
    """Temps ; pression ; puissance (décimales à la virgule), ligne finissant par ';'."""
    lines = ["Temps;Pression;Puissance;"]
    for i in range(N):
        lines.append(f"{i*2};{1 + i/100:.2f};{100 + i}".replace(".", ",") + ";")
    return _write(tmp_path, "\n".join(lines))


SETTINGS = {'delim': ';', 'unitdelim': ',', 'start': 0, 'columns': [],
            'sigNames': True, 'isFirstColIndex': True}


def _settings(**changes):
    return dict(SETTINGS, **changes)


# ---------------- découpage ----------------

def test_parse_with_time_column(txt_file):
    result = txt_import.parse_txt(txt_file, SETTINGS, 1.0)

    # colonne vide finale (ligne terminée par ';') ignorée
    assert result.channels == ["Pression", "Puissance", "channel3"]
    np.testing.assert_allclose(result.data["Time"][:3], [0, 2, 4])
    assert result.sampling == 2
    np.testing.assert_allclose(result.data["Pression"][:2], [1.00, 1.01])
    assert result.invalid_cells == 0


def test_parse_ignored_columns_and_start_row(txt_file):
    result = txt_import.parse_txt(txt_file, _settings(columns=[2, 3], start=10), 1.0)
    assert result.channels == ["Pression"]
    assert len(result.data) == N - 10
    assert result.data["Time"].iloc[0] == 20


def test_parse_without_names_or_time(txt_file):
    """Régression : « noms des voies » décoché faisait échouer le chargement."""
    result = txt_import.parse_txt(txt_file, _settings(sigNames=False, isFirstColIndex=False,
                                                      start=1, columns=[3]), 0.5)
    assert result.channels == ["channel0", "channel1", "channel2"]
    np.testing.assert_allclose(result.data["Time"][:3], [0, 0.5, 1.0])
    assert len(result.data) == N


def test_non_numeric_cells_become_nan(tmp_path):
    path = _write(tmp_path, "t;a\n0;1\n1;OVER\n2;3\n3;4")
    result = txt_import.parse_txt(path, SETTINGS | {'unitdelim': '.'}, 1.0)
    assert np.isnan(result.data["a"][1]) and result.invalid_cells == 1


@pytest.mark.parametrize("settings", [_settings(delim=","), _settings(unitdelim=".")])
def test_wrong_separator_is_an_error_when_strict(txt_file, settings):
    with pytest.raises(TxtDelimiterError):
        txt_import.parse_txt(txt_file, settings, 1.0, strict=True)


def test_wrong_decimal_gives_empty_channel_when_not_strict(txt_file):
    """Réglages du wizard : la voie est chargée vide (signalée dans l'aperçu)."""
    result = txt_import.parse_txt(txt_file, _settings(unitdelim="."), 1.0)
    assert not np.isfinite(result.data["Pression"]).any()


def test_direct_load_with_wrong_decimal_opens_wizard(ctrl, txt_file, monkeypatch):
    opened = []
    monkeypatch.setattr(ctrl.import_ctrl, "ImportWizard",
                        lambda path, params=None: opened.append(path))
    ctrl.import_ctrl.loaderSelect({"file_type": "TXT", "address": txt_file,
                                   "import_params": None})
    assert opened == [txt_file] and ctrl.workspace.files == []


@pytest.mark.parametrize("start", [N, None])
def test_nothing_selected_is_an_error(txt_file, start):
    with pytest.raises(TxtFormatError):
        txt_import.parse_txt(txt_file, _settings(start=start), 1.0)


def test_delimiter_detection_without_settings(tmp_path):
    path = _write(tmp_path, "a\tb\n1\t2\n3\t4\n5\t6")
    result = txt_import.parse_txt(path, {'delim': txt_import.DEFAULT_DELIMITERS,
                                         'sigNames': True}, 1.0)
    assert result.channels == ["a", "b"]


def test_max_rows(txt_file):
    assert len(txt_import.parse_txt(txt_file, SETTINGS, 1.0, max_rows=10).data) == 10


# ---------------- chargement (openTxt) ----------------

def test_open_txt_loads_what_parse_returns(ctrl, txt_file):
    ctrl.import_ctrl.openTxt(txt_file, SETTINGS)

    file_obj = ctrl.workspace.files[0]
    expected = txt_import.parse_txt(txt_file, SETTINGS, 1.0)
    assert [s.name for s in file_obj.signals] == expected.channels
    np.testing.assert_allclose(file_obj.signals[0].x, expected.data["Time"])
    np.testing.assert_allclose(file_obj.signals[0].y, expected.data["Pression"])
    assert file_obj.sampling == 2


def test_open_txt_without_names(ctrl, txt_file):
    ctrl.import_ctrl.openTxt(txt_file, _settings(sigNames=False, isFirstColIndex=False,
                                                 start=1, columns=[3]))
    file_obj = ctrl.workspace.files[0]
    assert len(file_obj.signals) == 3 and len(file_obj.signals[0].y) == N


def test_txt_channels_are_not_hidden(ctrl, txt_file):
    """Les données d'un .txt (puissance...) n'ont pas de plage : toutes affichées."""
    ctrl.import_ctrl.openTxt(txt_file, SETTINGS)
    assert all(s.visible for s in ctrl.workspace.files[0].signals)


# ---------------- aperçu du wizard ----------------

@pytest.fixture
def wizard(qapp, txt_file):
    dialog = ImportWizardDialog(txt_file, delimitor=';', unitDelim=',', default_sampling=1.0)
    yield dialog
    dialog.close()


def _curves(dialog):
    return [c.name() for c in dialog.preview_curves]


def _ok_enabled(dialog):
    from PyQt6.QtWidgets import QDialogButtonBox
    return dialog.buttonBox.button(QDialogButtonBox.StandardButton.Ok).isEnabled()


def _message(dialog):
    shown = dialog.preview_message in dialog.preview.getPlotItem().items
    return dialog.preview_message.toPlainText() if shown else None


def test_wizard_has_preview_graph(wizard):
    assert isinstance(wizard.preview, pg.PlotWidget)
    # « temps en première colonne » coché par défaut : Temps est l'axe des abscisses
    assert _curves(wizard) == ["Pression", "Puissance"]
    assert _message(wizard) is None
    assert wizard.preview_label.text().startswith("Aperçu : 2 voie(s), 50 point(s)")
    assert _ok_enabled(wizard)


def test_preview_matches_import(wizard, txt_file):
    wizard.TimeBox.setChecked(True)
    params = wizard.collect_params()
    expected = txt_import.parse_txt(txt_file, params, 1.0)
    assert _curves(wizard) == [c for c in expected.channels
                               if np.isfinite(expected.data[c]).any()]
    x, y = wizard.preview_curves[0].getOriginalDataset()
    np.testing.assert_allclose(x, expected.data["Time"])
    np.testing.assert_allclose(y, expected.data[expected.channels[0]])


def test_preview_follows_column_checkboxes(wizard):
    names_row = [wizard.importTable.item(0, j) for j in range(1, wizard.n_cols + 1)]
    puissance = [it for it in names_row if it.text() == "Puissance"][0]
    puissance.setCheckState(QtCore.Qt.CheckState.Unchecked)
    wizard.checkbox_changed(puissance)
    assert "Puissance" not in _curves(wizard)


def test_preview_follows_time_checkbox(wizard):
    wizard.TimeBox.setChecked(False)
    assert "Temps" in _curves(wizard)
    wizard.TimeBox.setChecked(True)
    assert "Temps" not in _curves(wizard)
    x, _ = wizard.preview_curves[0].getOriginalDataset()
    assert x[1] == 2                                     # temps lu dans le fichier


def test_preview_message_when_no_row_selected(wizard):
    first_row = wizard.importTable.item(1, 0)
    first_row.setCheckState(QtCore.Qt.CheckState.Unchecked)
    wizard.checkbox_changed(first_row)
    last_row = wizard.importTable.item(wizard.n_rows, 0)
    last_row.setCheckState(QtCore.Qt.CheckState.Unchecked)
    wizard.checkbox_changed(last_row)

    assert wizard.selected_rows == set()
    assert _curves(wizard) == [] and "Aucune donnée" in _message(wizard)
    assert wizard.preview_label.text() == "Aperçu indisponible"
    assert not _ok_enabled(wizard)


def test_preview_message_for_wrong_delimiter(wizard):
    wizard.DelimitorEdit.setText(",")
    wizard.newImportConfig()
    assert _curves(wizard) == []
    assert "séparateur" in _message(wizard)
    assert not _ok_enabled(wizard)


def test_preview_recovers_after_fixing_delimiter(wizard):
    wizard.DelimitorEdit.setText(",")
    wizard.newImportConfig()
    wizard.DelimitorEdit.setText(";")
    wizard.newImportConfig()
    assert _curves(wizard) and _message(wizard) is None and _ok_enabled(wizard)


def test_invalid_delimiter_does_not_crash(wizard):
    wizard.DelimitorEdit.setText(";;")
    wizard.newImportConfig()
    assert "invalide" in _message(wizard)


def test_column_without_numbers_is_reported(qapp, tmp_path):
    path = _write(tmp_path, "t;a;commentaire\n0;1;ok\n1;2;ok\n2;3;ok\n3;4;ok")
    dialog = ImportWizardDialog(path, delimitor=';', unitDelim='.')
    assert _curves(dialog) == ["a"]
    assert "1 voie(s) sans valeur numérique" in dialog.preview_label.text()
    dialog.close()


# ---------------- cas limites rencontrés sur des fichiers réels ----------------

def test_numeric_first_line_does_not_crash_wizard(qapp, tmp_path):
    """Fichier sans en-tête : la 1re ligne (numérique) servait de noms -> TypeError."""
    path = _write(tmp_path, "\n".join(f"{38230 + i % 2};{38231 - i % 2}" for i in range(20)))
    dialog = ImportWizardDialog(path, delimitor=';', unitDelim=',')
    dialog.NameBox.setChecked(False)
    dialog.TimeBox.setChecked(False)
    assert _curves(dialog) == ["channel0", "channel1"]
    dialog.close()


def test_preview_caps_number_of_curves(qapp, tmp_path):
    path = _write(tmp_path, ";".join(str(i) for i in range(200)) + "\n" +
                            ";".join(str(i) for i in range(200)))
    dialog = ImportWizardDialog(path, delimitor=';', unitDelim=',')
    dialog.TimeBox.setChecked(False)
    assert len(dialog.preview_curves) == ImportWizardDialog.PREVIEW_CHANNELS
    assert "premières voies tracées" in dialog.preview_label.text()
    dialog.close()


def test_unreadable_file_message(qapp, tmp_path):
    path = _write(tmp_path, "x" * 200000)              # champ plus long que la limite csv
    dialog = ImportWizardDialog(path, delimitor=';', unitDelim=',')
    assert "illisible" in _message(dialog) and not _ok_enabled(dialog)
    dialog.close()


# ---------------- boîte de dialogue d'ouverture ----------------

def test_file_dialog_filters(ctrl):
    """Qt sépare les filtres par ';;' : avec une virgule, seul le dernier motif (*.csv)
    était retenu et les .txt n'apparaissaient pas."""
    import re
    from ressources.custom_types import fileType
    for file_type, request in ctrl.import_ctrl.load_dict.items():
        _, filters = request.loader_label
        for name_filter in filters.split(";;"):
            # un filtre = un libellé et UNE parenthèse de motifs
            assert re.fullmatch(r"[^()]+\([^()]+\)", name_filter.strip()), name_filter
    _, txt_filters = ctrl.import_ctrl.load_dict[fileType.TXT].loader_label
    assert txt_filters.split(";;")[0].endswith("(*.txt)")
