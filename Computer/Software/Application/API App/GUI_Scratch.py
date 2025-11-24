##### GUI from Scratch

import os
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QComboBox, QCheckBox, QLabel, QSpacerItem, QSizePolicy, QFrame, QTextEdit, QFileDialog

class WineLauncher(QWidget):

    def __init__(self): 
        super().__init__()
        self.setWindowTitle("Wine EXE Launcher")
        self.resize(1024, 600)
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

        # Add the checkboxes below the label
        checkboxes = [
            self.create_checkbox("Wine"),
            self.create_checkbox("Vulkan"),
            self.create_checkbox("DXVK"),
            self.create_checkbox("VKD3D"),
            self.create_checkbox("Gamemode")
        ]
        for checkbox in checkboxes:
            chk_v.addWidget(checkbox)
            checkbox.stateChanged.connect(self.on_checkbox_state_changed)

        chk_v.setContentsMargins( 1, 1, 1, 1)
        return chk_v

    def init_ui(self):
        v = QVBoxLayout()

        # Create buttons
        self.b_selbase = self.create_button("Select The BasePrefix", self.sel_bprefix)
        self.b_exe = self.create_button("Select The G/Soft.exe", self.sel_exe)
        self.b_run = self.create_button("Launch and Analyze", self.launch_analyze_exe)

        # ComboBoxes
        self.modify_base = self.create_combo_box(["BasePrefix Options : None", "Create Base Prefix", "Delete Base Prefix", "Run WineCfg", "Install-Dlls"])
        self.modify_temp = self.create_combo_box(["Temp Prefix Options : None", "Create Temp Prefix", "Delete Temp Prefix"])
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

        log_h.addWidget(self.log, 1)
        log_h.addLayout(chk_v, 0)

        v.addLayout(log_h)

        self.setLayout(v)

    # GUI Part Done , Now For Connecting Methods Remain : --------------------------------------------------------------

    def sel_bprefix(self):

        base_prefix_dir = QFileDialog.getExistingDirectory(self, "Select Base Prefix Directory")
        if not base_prefix_dir:
            self.log.append("No directory selected.")
            return

        self.log.append(f"Base Prefix selected: {base_prefix_dir}")


    def sel_exe(self):

        exe_file, _ = QFileDialog.getOpenFileName(self, "Select G/Soft.exe", "", "Executable Files (*.exe)")
        if not exe_file:
            self.log.append("No executable selected.")
            return

        self.log.append(f"Executable selected: {exe_file}")


    def on_resolution_changed(self, index):
        selected_option = self.resolution.itemText(index)
        self.log.append(f"Resolution option selected: {selected_option}")
        # Additional logic goes here...


    def on_checkbox_state_changed(self, state):
        sender = self.sender()  # Get the checkbox that triggered the signal
        checkbox_label = sender.text()

        if state == Qt.Checked:
            self.log.append(f"{checkbox_label} is enabled.")
        else:
            self.log.append(f"{checkbox_label} is disabled.")


    def on_modify_base_changed(self, index):
        selected_option = self.modify_base.itemText(index)
        self.log.append(f"Base Prefix option selected: {selected_option}")
        # Additional logic goes here...

    def on_modify_temp_changed(self, index):
        selected_option = self.modify_temp.itemText(index)
        self.log.append(f"Temp Prefix option selected: {selected_option}")
        # Additional logic goes here...


    def launch_analyze_exe(self):

        self.log.append("Launching and analyzing EXE...")
        # Your logic goes here...
        self.log.append("Analysis completed.")

    # Method definitions below-----------------------------------------------------------------------------------------------
