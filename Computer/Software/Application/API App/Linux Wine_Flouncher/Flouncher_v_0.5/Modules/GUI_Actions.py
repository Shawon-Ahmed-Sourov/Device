import os
from PyQt5.QtWidgets import QWidget, QFileDialog
from PyQt5.QtCore import Qt

# Subsystem Imports
from GUI_UI import UIBuilder

from GUI_W_FileSystem import Prefix
from GUI_W_Runner1 import RunAnalyze

class WineLauncher(QWidget):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Wine EXE Launcher")
        self.resize(850, 450)
        
        # 1. State Management
        self.bprefix_path, self.exe_file, self.exe_path = None, None, None
        self.worker_thread = None

        # 2. Initialize UI Subsystem
        self.ui_builder = UIBuilder()  # Create The UI_Object
        self.ui_builder.setup_ui(self) # Call UI_Object_Function
        
        # 3. Connect Signals
        self._connect_signals()

    def _connect_signals(self):
        """Links UI elements to their functional logic"""
        self.btn_base.clicked.connect(self.sel_bprefix)
        self.btn_exe.clicked.connect(self.sel_exe)
        self.btn_run.clicked.connect(self.launchan)
        self.modify_base.currentIndexChanged.connect(self.on_modify_base_changed)
        self.modify_temp.currentIndexChanged.connect(self.on_modify_temp_changed)

    # --- Action Logic ---

    def on_checkbox_state_changed(self, state):
        status = "Enabled" if state == Qt.Checked else "Disabled"
        self.log.append(f"⚙️ {self.sender().text()}: {status}")


    def sel_bprefix(self):

        path = QFileDialog.getExistingDirectory(self, "Select Base Prefix")
        if path:
             self.bprefix_path = path
             self.log.append(f"📂 Base Prefix Set: {self.bprefix_path}")
        else : self.log.append("❌ Selection cancelled.")


    def sel_exe(self):

        file, _ = QFileDialog.getOpenFileName(self, "Select EXE", "", "Executables (*.exe)")
        if file:
            self.exe_file = file
            self.log.append(f"💻 EXE: {file}")

            self.exe_path = os.path.dirname(file)
            if os.path.isdir( os.path.join(self.exe_path, ".wine_temp_noverlay") ):
                    self.log.append(f"✅ Found Temp Prefix.\n")
            else :  self.log.append(f"❌ Not Found Temp Prefix 'wine_temp_noverlay'.\n")

        else : self.log.append("❌ Selection cancelled.") 


    def launchan(self):

        if not self.exe_file:    return self.log.append( "❌ Error: No EXE selected!" )
        self._start_task( RunAnalyze, ( self.exe_path, self.exe_file ), self.btn_run )

    def on_modify_temp_changed(self, index):

        mapping = {1: 4, 2: 3}
        if index in mapping:
            self._start_task( Prefix, ( mapping[index], self.exe_path, self.bprefix_path ), self.modify_temp )

    def on_modify_base_changed(self, index):

        if index == 1:
            self._start_task( Prefix, ( 1, self.exe_path, self.bprefix_path ), self.modify_base )


    def _start_task(self, worker_class, args, ui_element):

        ui_element.setEnabled(False)    # 2. Disable UI

        # 3. Initialize & Connect
        self.worker_thread = worker_class(*args)
        if hasattr(self.worker_thread, 'log'):  self.worker_thread.log.connect(self.log.append)
    
        # 4. Cleanup Logic
        def on_complete():
            ui_element.setEnabled(True)
            if hasattr(ui_element, 'setCurrentIndex'):    ui_element.setCurrentIndex(0)

        self.worker_thread.done.connect(on_complete)
        self.worker_thread.start()
