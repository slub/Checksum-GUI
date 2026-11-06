"""Optional desktop notifications using the desktop's available backend."""

import shutil
import sys

from PyQt6.QtCore import QProcess
from PyQt6.QtWidgets import QSystemTrayIcon


class DesktopNotifications:
    def __init__(self, window):
        self.window = window
        self.executable = shutil.which("notify-send") if sys.platform == "linux" else None
        self.tray = None

    def show(self, title, message):
        if self.executable:
            process = QProcess(self.window)
            process.finished.connect(process.deleteLater)
            process.errorOccurred.connect(process.deleteLater)
            process.start(self.executable, ["--app-name=chksmg", "--", title, message])
        elif QSystemTrayIcon.isSystemTrayAvailable() and QSystemTrayIcon.supportsMessages():
            if self.tray is None:
                self.tray = QSystemTrayIcon(self.window.windowIcon(), self.window)
                self.tray.setToolTip(title)
                self.tray.show()
            self.tray.showMessage(title, message)
