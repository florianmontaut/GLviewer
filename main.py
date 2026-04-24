# main.py

import sys
from PyQt6.QtWidgets import QApplication
from view.main_window import MainWindow
from controller.main_controller import MainController
from ressources import custom_viewer_settings
import qdarktheme

class App(QApplication):

    def __init__(self,sys_argv):

        super(App,self).__init__(sys_argv)
        qdarktheme.setup_theme("auto")
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
        dark=opts.get('dark_mode',False)

        if dark :
            palette     = qdarktheme.load_palette(theme="dark")
            stylesheet  = qdarktheme.load_stylesheet(theme="dark")
        else:
            palette     = qdarktheme.load_palette(theme="auto")
            stylesheet  = qdarktheme.load_stylesheet(theme="auto")

        self.setPalette(palette)
        self.setStyleSheet(stylesheet)


if __name__ == "__main__":
    app = App(sys.argv)
    sys.exit(app.exec())
