# -*- coding: utf-8 -*-
from PySide6.QtWidgets import QApplication, QWidget
from appUI import Ui_MBAutoFarmWidget
import os
import sys

from Theme import QtTheme_rc  # noqa: F401  注册 qrc 资源（图标、qss 等）
# import taskControl
from taskControl import taskControl
from updater import Updater

APP_VERSION = "1.1.1"
APP_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

if __name__ == "__main__":
    
    appQT = QApplication(sys.argv)
    appWidget = QWidget()
    appUi = Ui_MBAutoFarmWidget(configPath=APP_CONFIG_PATH, appVersion=APP_VERSION)
    appUi.setupUi(appWidget)
    appTaskControl = taskControl(APP_CONFIG_PATH, appUi)
    appUi.setTaskControl(appTaskControl)

    qss_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "Theme", "theme", "Flat", "Dark", "Blue", "Pink.qss")
    with open(qss_path, "r", encoding="utf-8") as f:
        appQT.setStyleSheet(f.read())

    appWidget.show()
    appUi.log_printf("INFO", "MBAutoFarm: v%s", APP_VERSION)
    Updater(APP_VERSION, appUi.log_printf, appWidget).check_async()
    sys.exit(appQT.exec())