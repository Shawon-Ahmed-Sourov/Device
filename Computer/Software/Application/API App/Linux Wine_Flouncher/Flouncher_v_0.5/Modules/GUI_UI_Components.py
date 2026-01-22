
#-----The Visual UI Skeleton & It's Components

from GUI_UI_Utilities import UIUtils

from PyQt5.QtWidgets import QVBoxLayout, QComboBox, QPushButton, QTextEdit, QHBoxLayout, QCheckBox


class UIBuilder:
    def setup_ui(self, window):
        main_v = QVBoxLayout(window)
        
        # Elements
        window.log = QTextEdit(readOnly=True)
        window.modify_base = QComboBox()
        window.modify_base.addItems(["BasePrefix Options : None", "Create Base Prefix", "Delete Base Prefix", "Run WineCfg", "Install-Dlls"])
        
        window.modify_temp = QComboBox()
        window.modify_temp.addItems(["Temp Prefix Options : None", "Delete", "Create"])
        
        window.resolution = QComboBox()
        window.resolution.addItems(["Resolution : None", "600 x 600", "1024 x 768", "1280 x 720"])

        window.btn_base = QPushButton("Select The BasePrefix")
        window.btn_exe  = QPushButton("Select The G-Soft.exe")
        window.btn_run  = QPushButton("Launch and Analyze")

        # Assembly
        main_v.addLayout(UIUtils.row(window.modify_base, window.btn_base, window.btn_exe))
        main_v.addLayout(UIUtils.row(window.modify_temp, window.resolution, window.btn_run))
        main_v.addWidget(UIUtils.sep())


        # Component : CheckBox
        log_h = QHBoxLayout()
        chk_v = QVBoxLayout()
        for label in ["Wine", "Vulkan", "DXVK", "VKD3D", "Gamemode"]:
            cb = QCheckBox(label, stateChanged=window.on_checkbox_state_changed)
            chk_v.addWidget(cb)
        
        log_h.addWidget(window.log, 1) 
        log_h.addLayout(chk_v, 0)
        main_v.addLayout(log_h)

