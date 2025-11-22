import sys
from PyQt5.QtWidgets import QApplication
from GUI import WineLauncher

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = WineLauncher()
    w.show()
    sys.exit(app.exec_())
