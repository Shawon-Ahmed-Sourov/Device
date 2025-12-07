import os, subprocess
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QFrame
from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QPushButton, QCheckBox, QFileDialog, QTextEdit

from Workers import InstallDllsWorker, TemprefixWorker, DeleteTempPrefixWorker, AnalyzeAndRunExeWorker

class WineLauncher(QWidget):
    DXVK_FILES = ["d3d11.dll", "dxgi.dll"]

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Wine EXE Launcher")
        self.resize(900, 550)
        self.wine = "wine"
        self.exe = self.temp = self.base = ""
        self.vulkan_ok = self.dxvk_ok = False
        self.build_ui()
        self.check_vulkan()

    def sep(self):  line = QFrame() ; line.setFrameShape(QFrame.HLine) ; line.setFrameShadow(QFrame.Sunken) ; return line
    def row(self, *btns): h = QHBoxLayout(); [h.addWidget(b) for b in btns]; return h

    def build_ui(self):
        v = QVBoxLayout() ; mk = lambda t, fn, en=True: QPushButton(t, clicked=fn, enabled=en)

        # Buttons
        self.b_base = mk("Create A BasePrefix", self.create_base)
        self.b_modb = mk("Modify BasePrefix", self.modify_base, False)
        self.b_selbase = mk("Select The BasePrefix", self.sel_prefix)
        self.b_del = mk("Delete Temp Prefix", self.del_temp, False)
        self.b_temp = mk("Create Temp Prefix", self.mk_temp, False)
        self.b_exe = mk("Select The G/Soft.exe", self.sel_exe)
        self.b_inst = mk("Install Dlls in BasePrefix", self.inst_deps, False)
        self.b_modify_temp = mk("Modify Temp Prefix", self.modify_temp, False)
        self.b_sel_resolution = mk("Select The Resolution", self.sel_resolution)
        self.b_run = mk("Launch and Analyze", self.launch_analyze_exe, False)

        # Layout Setup
        for r in (
            self.row(self.b_base, self.b_modb, self.b_selbase),
            self.row(self.b_del, self.b_temp, self.b_exe),
            self.row(self.b_inst, self.b_modify_temp, self.b_sel_resolution),
            self.row(self.b_run)
        ):
            v.addLayout(r) ; v.addWidget(self.sep())

        # Logging & Checkboxes
        log_h = QHBoxLayout() ; chk_v = QVBoxLayout()
        self.chk_wine, self.chk_vulkan, self.chk_dxvk, self.chk_vkd3d, self.chk_gamemode = [QCheckBox(t) for t in ("Wine", "Vulkan", "DXVK", "VKD3D", "Gamemode")]
        for c in (self.chk_wine, self.chk_vulkan, self.chk_dxvk, self.chk_vkd3d, self.chk_gamemode): chk_v.addWidget(c)

        self.log = QTextEdit(readOnly=True)
        log_h.addLayout(chk_v) ; log_h.addWidget(self.log)
        v.addLayout(log_h)

        self.setLayout(v)

    # GUI Part Done , Now For Connecting Methods Definition : --------------------------------------------------------------

    def sel_prefix(self):
        d = QFileDialog.getExistingDirectory(self, "Select Base Wine Prefix")
        if d:
            self.base = d
            self.log.append(f"📂 Base Prefix: {d}")
            self.b_temp.setEnabled(bool(self.exe))
            self.b_inst.setEnabled(True)
            self.check_dxvk()

    def mk_temp(self):
        if os.path.exists(self.temp):    self.log.append(f"ℹ️ Temp Prefix already exists at {self.temp}")
        else:
            self.b_temp.setEnabled(False)
            self.log.append("⏳ Creating Temp Prefix...")
            self.worker = TemprefixWorker(self.exe, self.base, self.temp, self.wine)
            self.worker.log.connect(self.log.append)
            self.worker.done.connect(lambda ok: [self.b_temp.setEnabled(True), self.b_del.setEnabled(ok), self.update_run_button()])
            self.worker.start()

    def del_temp(self):
        if not os.path.exists(self.temp):     self.log.append("ℹ️ No Temp Prefix found.")
        else:
            self.worker = DeleteTempPrefixWorker(self.temp)
            self.worker.log.connect(self.log.append)
            self.worker.start()
            self.b_del.setEnabled(False)
            self.b_run.setEnabled(False)

    # EXE Operations
    def sel_exe(self):
        p, _ = QFileDialog.getOpenFileName(self, "Select G/Soft.exe", "", "EXE files (*.exe)")
        if p:
            self.exe = p
            self.temp = os.path.join(os.path.dirname(p), ".wine_temp_overlay")
            self.log.append(f"📂 Selected EXE: {p}")
            self.b_del.setEnabled(os.path.exists(self.temp))
            self.b_temp.setEnabled(bool(self.base))
            self.update_run_button()

    def update_run_button(self):    self.b_run.setEnabled(bool(self.exe) and os.path.exists(self.temp))

    def launch_analyze_exe(self):
        if self.exe and os.path.exists(self.temp):
            self.worker = AnalyzeAndRunExeWorker(self.exe, self.temp, self.wine)
            self.worker.log.connect(self.log.append)
            self.worker.started_signal.connect(self.log.append)
            self.worker.start()
        else:    self.log.append("❌ EXE or Temp Prefix not ready.")

    # Dependency and Vulkan Checks
    def check_vulkan(self):
        try:
            out = subprocess.run(["vulkaninfo"], capture_output=True, text=True, timeout=5).stdout
            self.vulkan_ok = "deviceName" in out
            self.log.append("✅ Vulkan supported." if self.vulkan_ok else "❌ Vulkan not detected.")
        except Exception as e:    self.log.append(f"❌ Vulkan check failed: {e}")

    def check_dxvk(self):
        s32 = os.path.join(self.base, "drive_c", "windows", "system32")
        self.dxvk_ok = all(os.path.exists(os.path.join(s32, f)) for f in self.DXVK_FILES)
        self.log.append("✅ DXVK detected." if self.dxvk_ok else "❌ DXVK not found.")

    def inst_deps(self):
        if not self.base:     self.log.append("❌ Select a Base Prefix first.")
        else:
            self.log.append("⏳ Launching Winetricks...")
            self.worker = InstallDllsWorker(self.base)
            self.worker.log.connect(self.log.append)
            self.worker.start()

    def create_base(self):    self.log.append("⚡ Create a Base Prefix: Not yet implemented.")
    def modify_base(self):    self.log.append("⚡ Cleaning and updating Base Prefix: Not yet implemented.")
    
    def modify_temp(self):    self.log.append("⚡ Modify Temp Prefix: Not yet implemented.")    
    def sel_resolution(self):    self.log.append("⚡ Select The Resolution: Not yet implemented.")
