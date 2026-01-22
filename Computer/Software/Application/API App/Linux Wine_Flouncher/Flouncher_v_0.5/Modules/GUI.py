import sys
from PyQt5.QtWidgets import QApplication
from GUI_Actions import WineLauncher

def main():
    
    app = QApplication(sys.argv)

    # Launch the Controller
    launcher = WineLauncher()
    launcher.show()

    # Execute the event loop
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
