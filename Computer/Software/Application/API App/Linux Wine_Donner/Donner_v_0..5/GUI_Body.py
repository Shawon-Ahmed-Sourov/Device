import sys
from PyQt5.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QComboBox, QPushButton, 
    QTextEdit, QCheckBox, QFrame
)

class UIUtils:
    @staticmethod
    def row(*widgets):
        layout = QHBoxLayout()
        for w in widgets: layout.addWidget(w)
        return layout

    @staticmethod
    def sep():
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        return line

class UIBuilder:    
    def setup_ui(self, window):
        main_v = QVBoxLayout(window)

        window.log = QTextEdit(readOnly=True)
        window.modify_base = QComboBox()
        window.modify_base.addItems([
            "BasePrefix Options : None", "Create Base Prefix", 
            "Delete Base Prefix", "Run WineCfg", "Install-Dlls"
        ])
        
        window.modify_temp = QComboBox()
        window.modify_temp.addItems(["Temp Prefix Options : None", "Delete", "Create"])
        
        window.resolution = QComboBox()
        window.resolution.addItems(["Resolution : None", "600 x 600", "1024 x 768", "1280 x 720"])

        window.btn_base = QPushButton("Select The BasePrefix")
        window.btn_exe  = QPushButton("Select The G-Soft.exe")
        window.btn_run  = QPushButton("Launch and Analyze")

        main_v.addLayout(UIUtils.row(window.modify_base, window.btn_base, window.btn_exe))
        main_v.addLayout(UIUtils.row(window.modify_temp, window.resolution, window.btn_run))
        main_v.addWidget(UIUtils.sep())

        log_h, chk_v = QHBoxLayout(), QVBoxLayout()
        window.checkboxes = {} 
        for label in ["Gamemode", "Vulkan", "VKD3D", "DXVK"]:
            cb = QCheckBox(label)
            if hasattr(window, 'on_checkbox_state_changed'):
                cb.stateChanged.connect(window.on_checkbox_state_changed)
            chk_v.addWidget(cb)
            window.checkboxes[label] = cb
        
        chk_v.addStretch() 
        log_h.addWidget(window.log, 1) 
        log_h.addLayout(chk_v, 0)      
        main_v.addLayout(log_h)
