# Date : 24 Nov 2025
# main.py
import sys
from PyQt5.QtWidgets import QApplication
from GUI import WineLauncher

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = WineLauncher()
    window.show()
    sys.exit(app.exec_())
