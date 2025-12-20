import os
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (QWidget, QLabel, QFrame, QMainWindow, QApplication, QHBoxLayout, 
                             QVBoxLayout, QComboBox, QCheckBox, QTextEdit, QFileDialog, 
                             QPushButton, QSpacerItem, QSizePolicy)
from Workers import Prefix, RunAnalyze

class WineLauncher(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Wine EXE Launcher")
        self.resize(850, 450)
        
        # State Variables
        self.bprefix_path = self.tprefix_path = self.exe_file = self.exe_path = self.BepInEx_path = None
        self.worker_thread = None
        
        self.init_ui()

    def init_ui(self):
        main_v = QVBoxLayout(self)

        # 1. CREATE LOG FIRST (so other widgets can reference it immediately)
        self.log = QTextEdit(readOnly=True)

        # 2. CREATE COMBOBOXES
        # Now, when currentIndexChanged fires, self.log already exists.
        self.modify_base = QComboBox(currentIndexChanged=self.on_modify_base_changed)
        self.modify_base.addItems(["BasePrefix Options : None", "Create Base Prefix", "Delete Base Prefix", "Run WineCfg", "Install-Dlls"])
        
        self.modify_temp = QComboBox(currentIndexChanged=self.on_modify_temp_changed)
        self.modify_temp.addItems(["Temp Prefix Options : None", "Delete", "Create"])
        
        self.resolution = QComboBox(currentIndexChanged=self.on_resolution_changed)
        self.resolution.addItems(["Resolution : None", "600 x 600", "1024 x 768", "1280 x 720"])

        # 3. CREATE BUTTONS
        btn_base = QPushButton("Select The BasePrefix", clicked=self.sel_bprefix)
        btn_exe  = QPushButton("Select The G-Soft.exe", clicked=self.sel_exe)
        btn_run  = QPushButton("Launch and Analyze", clicked=self.launchan)

        # Layout Assembly
        main_v.addLayout(self.row(self.modify_base, btn_base, btn_exe))
        main_v.addLayout(self.row(self.modify_temp, self.resolution, btn_run))
        main_v.addWidget(self.sep())

        # Log and Checkboxes
        log_h = QHBoxLayout()
        chk_v = QVBoxLayout()
        for label in ["Wine", "Vulkan", "DXVK", "VKD3D", "Gamemode"]:
            cb = QCheckBox(label, stateChanged=self.on_checkbox_state_changed)
            chk_v.addWidget(cb)
        
        log_h.addWidget(self.log, 1)
        log_h.addLayout(chk_v, 0)
        main_v.addLayout(log_h)

    # --- UI Helpers ---
    def row(self, *widgets):
        layout = QHBoxLayout()
        for w in widgets: layout.addWidget(w)
        return layout

    def sep(self):
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        return line

    # --- Logic ---
    def start_worker(self, worker_class, **kwargs):
        """Generic helper to handle worker initialization and cleanup"""
        self.worker_thread = worker_class(**kwargs)
        self.worker_thread.log.connect(self.log.append)
        self.worker_thread.done.connect(lambda success: self.log.append("✅ Success!" if success else "❌ Failed."))
        self.worker_thread.start()

    def sel_bprefix(self):
        self.bprefix_path = QFileDialog.getExistingDirectory(self, "Select Base Prefix")
        self.log.append(f"📂 Base Prefix: {self.bprefix_path}" if self.bprefix_path else "No directory selected.")

    def sel_exe(self):
        file, _ = QFileDialog.getOpenFileName(self, "Select EXE", "", "Executables (*.exe)")
        if not file: return self.log.append("❌ No selection.")
        
        self.exe_file = file
        self.exe_path = os.path.dirname(file)
        self.tprefix_path = os.path.join(self.exe_path, ".wine_temp_noverlay", "merged")
        
        # Fast search for BepInEx
        self.BepInEx_path = next((os.path.join(r, "BepInEx.dll") for r, d, f in os.walk(self.exe_path) if "BepInEx.dll" in f), None)
        
        self.log.append(f"💻 EXE: {file}\n📂 Path: {self.exe_path}\n✅ Prefix: {self.tprefix_path}")
        if self.BepInEx_path: self.log.append(f"✅ BepInEx: {self.BepInEx_path}")

    def on_modify_base_changed(self, index):
        opt = self.modify_base.currentText()
        if "Create" in opt:
            self.start_worker(Prefix, num=1, exe_path=self.exe_path, base_dir=os.path.dirname(__file__))
        elif "Delete" in opt: self.log.append("Feature pending...")

    def on_modify_temp_changed(self, index):
        opt = self.modify_temp.currentText()
        num_map = {"Create": 3, "Delete": 4}
        if opt in num_map:
            self.start_worker(Prefix, num=num_map[opt], exe_path=self.exe_path, bprefix_path=self.bprefix_path)

    def launchan(self):
        if not self.exe_file: return self.log.append("❌ Select an EXE first.")
        self.start_worker(RunAnalyze, exe_path=self.exe_path, exe_file=self.exe_file, tprefix_path=self.tprefix_path)

    def on_resolution_changed(self, index): self.log.append(f"Res: {self.resolution.currentText()}")
    
    def on_checkbox_state_changed(self, state):
        self.log.append(f"{self.sender().text()}: {'Enabled' if state == Qt.Checked else 'Disabled'}")
