
# GUI_UI_Components.py
# Combined UI : Skeleton, Components & Utilities

from PyQt5.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QComboBox,
    QPushButton, QTextEdit, QCheckBox, QFrame
)

class UIUtils:    # Helper utilities for layout and styling.
    
    @staticmethod
    def row(*widgets):
        layout = QHBoxLayout()
        for w in widgets:    layout.addWidget(w)
        return layout

    @staticmethod
    def sep():
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        return line


class UIBuilder:    #  The Visual UI Skeleton and Its Components.
    
    def setup_ui(self, window):
        # Main vertical layout
        main_v = QVBoxLayout(window)

        
        # --- UI Elements ---
        window.log = QTextEdit(readOnly=True)
        
        window.modify_base = QComboBox()
        window.modify_base.addItems([
            "BasePrefix Options : None", 
            "Create Base Prefix", 
            "Delete Base Prefix", 
            "Run WineCfg", 
            "Install-Dlls"
        ])
        
        window.modify_temp = QComboBox()
        window.modify_temp.addItems([
            "Temp Prefix Options : None", 
            "Delete", 
            "Create"
        ])
        
        window.resolution = QComboBox()
        window.resolution.addItems([
            "Resolution : None", 
            "600 x 600", 
            "1024 x 768", 
            "1280 x 720"
        ])

        window.btn_base = QPushButton("Select The BasePrefix")
        window.btn_exe  = QPushButton("Select The G-Soft.exe")
        window.btn_run  = QPushButton("Launch and Analyze")


        # --- Assembly using Utilities ---
        main_v.addLayout(UIUtils.row(window.modify_base, window.btn_base, window.btn_exe))
        main_v.addLayout(UIUtils.row(window.modify_temp, window.resolution, window.btn_run))
        main_v.addWidget(UIUtils.sep())


        # --- Component : CheckBox & Log Area ---
        log_h = QHBoxLayout()
        chk_v = QVBoxLayout()
        
        for label in ["Wine", "Vulkan", "DXVK", "VKD3D", "Gamemode"]:
            # Note: window.on_checkbox_state_changed must be defined in your main Logic class
            cb = QCheckBox(label, stateChanged=window.on_checkbox_state_changed)
            chk_v.addWidget(cb)
        
        log_h.addWidget(window.log, 1) # Log takes priority expansion
        log_h.addLayout(chk_v, 0)      # Checkboxes stay at minimum width
        main_v.addLayout(log_h)

