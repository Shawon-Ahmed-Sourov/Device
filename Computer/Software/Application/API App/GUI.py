import os
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QComboBox, QCheckBox, QLabel, QSpacerItem, QSizePolicy, QFrame, QTextEdit, QFileDialog
from Workers import Prefix

from PyQt5.QtCore import QThread, pyqtSignal

#################################################################
########## The QThreaded Working Class
#################################################################

class BepInExPath_Searcher(QThread):
    result_signal = pyqtSignal(str) ; log_signal = pyqtSignal(str)     # Signaling results 2MThread & logs 2MThread

    def __init__(self, exe_path):
        super().__init__()
        self.exe_path = exe_path

    def run(self):
        for root, dirs, files in os.walk(self.exe_path):
            if "BepInEx" in dirs:
                core_path = os.path.join(root, "BepInEx", "core")
                if os.path.isdir(core_path) and "BepInEx.dll" in os.listdir(core_path):
                    bep_path = os.path.join(core_path, "BepInEx.dll")
                    self.log_signal.emit(f"✅ BepInEx.dll found: {bep_path}")
                    self.result_signal.emit(bep_path) ; return
        self.log_signal.emit("❌ BepInEx.dll not found in the expected directory.")

#################################################################

class WineLauncher(QWidget):

    def __init__(self): 
        super().__init__()
        self.setWindowTitle("Wine EXE Launcher")
        self.resize(1024, 600)

        self.bprefix_path = None; self.temp_prefix_path = None

        self.exe_file = None ; self.exe_path = None; self.BepInEx_path = None

        self.init_ui()

    def sep(self):    line = QFrame(); line.setFrameShape(QFrame.HLine); line.setFrameShadow(QFrame.Sunken); return line

    def row(self, *widgets):
        layout = QHBoxLayout()
        for widget in widgets : layout.addWidget(widget) 
        return layout

    def create_button(self, label, fn, enabled=True):   return QPushButton(label, clicked=fn, enabled=enabled)
    def create_combo_box(self, items):    combo = QComboBox(self); combo.addItems(items); return combo
    def create_checkbox(self, label):    return QCheckBox(label)
    def create_text_edit(self):    log = QTextEdit(readOnly=True); return log

    def create_checkbox_group(self):
        chk_v = QVBoxLayout()
        
        checkboxes = [ # Add the checkboxes below the label
            self.create_checkbox("Wine"),
            self.create_checkbox("Vulkan"),
            self.create_checkbox("DXVK"),
            self.create_checkbox("VKD3D"),
            self.create_checkbox("Gamemode")
        ]
        for checkbox in checkboxes:
            chk_v.addWidget(checkbox) ; checkbox.stateChanged.connect(self.on_checkbox_state_changed)

        chk_v.setContentsMargins( 1, 1, 1, 1)
        return chk_v

    def init_ui(self):
        v = QVBoxLayout()

        # Create buttons
        self.b_selbase = self.create_button("Select The BasePrefix", self.sel_bprefix)
        self.b_exe = self.create_button("Select The G-Soft.exe", self.sel_exe)
        self.b_run = self.create_button("Launch and Analyze", self.launch_analyze_exe)

        # ComboBoxes
        self.modify_base = self.create_combo_box(["BasePrefix Options : None", "Create Base Prefix", "Delete Base Prefix", "Run WineCfg", "Install-Dlls"])
        self.modify_temp = self.create_combo_box(["Temp Prefix Options : None", "Delete", "Create"])
        self.resolution = self.create_combo_box(["Resolution : None", "600 x 600", "1024 x 768", "1280 x 720"])

        # Connect ComboBox signals to methods
        self.modify_base.currentIndexChanged.connect(self.on_modify_base_changed)
        self.modify_temp.currentIndexChanged.connect(self.on_modify_temp_changed)
        self.resolution.currentIndexChanged.connect(self.on_resolution_changed)

        # Layout for buttons and combo boxes
        for layout in [
            self.row(self.modify_base, self.b_selbase, self.b_exe),
            self.row(self.modify_temp, self.resolution, self.b_run)
        ]:
            v.addLayout(layout)

        v.addWidget(self.sep())

        # Checkbox group
        log_h = QHBoxLayout()
        chk_v = self.create_checkbox_group()

        # Text Edit for log
        self.log = self.create_text_edit()

        log_h.addWidget(self.log, 1) ; log_h.addLayout(chk_v, 0)

        v.addLayout(log_h)

        self.setLayout(v)

    # GUI Part Done , Now For Connecting Methods Definition : --------------------------------------------------------------

    def sel_exe(self):

        exe_file, _ = QFileDialog.getOpenFileName(self, "Select G/Soft.exe", "", "Executable Files (*.exe)")
        if not exe_file:    self.log.append("No executable selected.") ; return

        self.log.append(f"💻Executable selected: {exe_file}")

        self.exe_path = os.path.dirname(exe_file); self.log.append(f"📂Executable path: {self.exe_path}")
        
        self.worker = BepInExPath_Searcher(self.exe_path) ; self.worker.log_signal.connect(self.log.append)  # Create the worker & Connect log_signal to the QTextEdit log
        self.worker.result_signal.connect(lambda path: (setattr(self, 'BepInEx_path', path),    self.log.append(f"✅ Saved BepInEx path: {self.BepInEx_path}")))
        self.worker.start() # Start the worker thread


    def sel_bprefix(self):

        self.bprefix_path = QFileDialog.getExistingDirectory(self, "Select Base Prefix Directory")
        if not self.bprefix_path: self.log.append("No directory selected."); return
        self.log.append(f"📂 Base Prefix selected: {self.bprefix_path}")
        

    def on_resolution_changed(self, index):
        selected_option = self.resolution.itemText(index)
        self.log.append(f"Resolution option selected: {selected_option}")
        # Additional logic goes here...


    def on_checkbox_state_changed(self, state):
        sender = self.sender()  # Get the checkbox that triggered the signal
        checkbox_label = sender.text()

        if state == Qt.Checked: self.log.append(f"{checkbox_label} is enabled.")
        else:                   self.log.append(f"{checkbox_label} is disabled.")



    def on_modify_temp_changed(self, index):
        temp_action = self.modify_temp.itemText(index)
        self.log.append(f"\n\nTemp Prefix option selected: {temp_action}")

        if temp_action == "Delete" :
            self.log.append("Starting Wine Prefix Deletion...")
            self.worker_thread = Prefix( num =4,    exe_path=self.exe_path )
            self.worker_thread.log.connect( self.log.append )
            self.worker_thread.done.connect( lambda success:
                self.log.append("✅ Wine prefix deleted successfully!" if success else "❌ Wine prefix deletion failed."))
            self.worker_thread.start()

        elif temp_action == "Create" :

            self.log.append("Starting Wine Prefix creation...")
            self.worker_thread = Prefix( num =3, exe_path=self.exe_path, bprefix_path=self.bprefix_path )
            self.worker_thread.log.connect(self.log.append)
            self.worker_thread.done.connect( lambda success:
                self.log.append( "✅ Wine prefix created successfully!\n" if success else "❌ Wine prefix creation failed.\n"))
            self.worker_thread.start()
            
        else : pass 


    def on_modify_base_changed(self, index):
        base_option = self.modify_base.itemText(index)
        self.log.append(f"Base Prefix option selected: {base_option}")

        if base_action == "Delete" :
            self.log.append("Working On Deleting Existing BasePrefix")
            # worker_class_thread( self.bprefix_path )

        elif base_action == "Create" :
            self.log.append("Working On Creating BasePrefix")
            
        else : pass 

    def launch_analyze_exe(self):    self.log.append("Launching EXE...")
