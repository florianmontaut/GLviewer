# main.py

import sys
from PyQt6.QtWidgets import QApplication
from view.main_window import MainWindow
from controller.main_controller import MainController
from ressources import custom_viewer_settings, theme
import qdarktheme

# Cases à cocher des arbres : qdarktheme les dessine en 18 px alors que le style Windows
# leur réserve moins de place ; la case et l'icône voisine étaient alors dessinées deux
# fois, décalées. Taille fixée à celle du style natif.
ITEM_VIEW_QSS = "QAbstractItemView::indicator { width: 14px; height: 14px; }"


class App(QApplication):

    def __init__(self,sys_argv):

        super(App,self).__init__(sys_argv)
        # style de qdarktheme (icônes standard) ; le thème lui-même est appliqué par
        # toggle_theme dès la lecture des options
        qdarktheme.setup_theme("dark" if theme.is_dark() else "light",
                               additional_qss=ITEM_VIEW_QSS)
        application_params = custom_viewer_settings.params

        # Création de la fenêtre principale
        window = MainWindow()
        # Contrôleur principal MVC
        controller = MainController(window,application_params)
        controller.menu_ctrl.newOptions.connect(self.toggle_theme)
        controller.menu_ctrl.newOptions.emit(controller.menu_ctrl.params)
        # Affichage
        window.show()

    def toggle_theme(self,opts) -> None:
        # couleurs, feuille de style et icônes : ressources/theme.py
        theme.apply(self, opts.get('dark_mode',False), extra_qss=ITEM_VIEW_QSS)


if __name__ == "__main__":
    app = App(sys.argv)
    sys.exit(app.exec())
