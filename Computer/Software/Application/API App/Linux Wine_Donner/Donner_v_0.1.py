# Date : 03 OCT 2025
# Flouncher_v_0.1.py
# Approach : Template Creation by Copy Pasting

import os, sys, shutil, subprocess, tempfile
from PyQt5.QtWidgets import QApplication, QWidget, QPushButton, QLabel, QVBoxLayout, QFileDialog, QTextEdit
from PyQt5.QtCore import QThread, pyqtSignal

# ---------- Worker Thread for Temp Prefix ----------
class PrefixWorker(QThread):
    log = pyqtSignal(str)
    progress = pyqtSignal(str)
    finished = pyqtSignal(bool, str)  # success, temp_prefix path

    def __init__(self, base_prefix, wine_binary, exe_dir):
        super().__init__()
        self.base_prefix = base_prefix
        self.wine_binary = wine_binary
        self.exe_dir = exe_dir
        self.temp_prefix = None

    def run(self):
        try:
            self.temp_prefix = os.path.join(self.exe_dir, "wine_temp_prefix")
            if os.path.exists(self.temp_prefix):
                shutil.rmtree(self.temp_prefix)
            os.makedirs(self.temp_prefix, exist_ok=True)

            self.log.emit(f"📁 Copying base prefix to {self.temp_prefix}...")

            # Try rsync first
            rsync_available = shutil.which("rsync") is not None
            if rsync_available:
                rsync_cmd = [
                    "rsync", "-aHAX", "--info=progress2", "--exclude=dosdevices/*",
                    f"{self.base_prefix}/", f"{self.temp_prefix}/"
                ]
                process = subprocess.Popen(rsync_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                for line in process.stdout:
                    line = line.strip()
                    if line:
                        self.progress.emit(f"📦 {line}")
                process.wait()
                if process.returncode != 0:
                    self.log.emit("⚠️ Rsync completed with warnings, continuing...")
                else:
                    self.log.emit("✅ Base prefix copied via rsync.")
            else:
                # Fallback to shutil
                self.log.emit("⚠️ Rsync not found, copying with shutil.copytree...")
                def copytree(src, dst):
                    for item in os.listdir(src):
                        s = os.path.join(src, item)
                        d = os.path.join(dst, item)
                        if os.path.isdir(s):
                            shutil.copytree(s, d, symlinks=True)
                        else:
                            shutil.copy2(s, d)
                copytree(self.base_prefix, self.temp_prefix)
                self.log.emit("✅ Base prefix copied via shutil.")

            # Ensure dosdevices exist
            dosdevices = os.path.join(self.temp_prefix, "dosdevices")
            os.makedirs(dosdevices, exist_ok=True)
            for drive, target in [("c:", "../drive_c"), ("z:", "/")]:
                drive_path = os.path.join(dosdevices, drive)
                if not os.path.exists(drive_path):
                    try:
                        os.symlink(target, drive_path)
                    except (OSError, NotImplementedError):
                        os.makedirs(drive_path, exist_ok=True)
                        self.log.emit(f"⚠️ Symlink for {drive} failed, created as directory.")

            # Initialize Wine prefix
            self.log.emit("⚙️ Initializing Wine prefix...")
            env = os.environ.copy()
            env["WINEPREFIX"] = self.temp_prefix
            subprocess.run([self.wine_binary, "wineboot", "-u"], env=env, cwd=self.exe_dir, check=True)
            subprocess.run([self.wine_binary, "reg", "add",
                            r"HKEY_CURRENT_USER\Software\Wine\Version",
                            "/ve", "/d", "win10", "/f"], env=env, check=True)

            self.log.emit("✅ Temp Prefix initialized and set to Windows 10.")
            self.finished.emit(True, self.temp_prefix)

        except Exception as e:
            self.log.emit(f"❌ Failed to create Temp Prefix: {e}")
            self.finished.emit(False, "")

# ---------- Main GUI ----------
class WineLauncher(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Unity EXE Wine Launcher")
        self.setGeometry(300, 300, 800, 600)

        self.exe_path = ""
        self.game_dir = ""
        self.temp_prefix = ""
        self.base_prefix = ""
        self.vulkan_supported = False
        self.dxvk_installed = False
        self.wine_binary = "wine"
        self.prefix_worker = None

        self.init_ui()
        self.check_vulkan_support()

    def init_ui(self):
        layout = QVBoxLayout()

        self.select_btn = QPushButton("Select Game EXE")
        self.select_btn.clicked.connect(self.select_exe)
        layout.addWidget(self.select_btn)

        self.path_label = QLabel("Selected: None")
        layout.addWidget(self.path_label)

        self.prefix_btn = QPushButton("Select Base Prefix")
        self.prefix_btn.setEnabled(False)
        self.prefix_btn.clicked.connect(self.select_base_prefix)
        layout.addWidget(self.prefix_btn)

        self.prefix_label = QLabel("Base Prefix: None")
        layout.addWidget(self.prefix_label)

        self.vulkan_status = QLabel("Vulkan Support: Not Checked")
        layout.addWidget(self.vulkan_status)

        self.analyze_btn = QPushButton("Analyze EXE (Detect Missing DLLs)")
        self.analyze_btn.clicked.connect(self.analyze_exe)
        layout.addWidget(self.analyze_btn)

        self.install_btn = QPushButton("Install Missing DLLs (via winetricks)")
        self.install_btn.clicked.connect(self.install_dependencies)
        layout.addWidget(self.install_btn)

        self.launch_btn = QPushButton("Launch Game")
        self.launch_btn.clicked.connect(self.launch_game)
        layout.addWidget(self.launch_btn)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        layout.addWidget(self.log_output)

        self.setLayout(layout)

    # ---------- GUI Actions ----------
    def select_exe(self):
        exe_path, _ = QFileDialog.getOpenFileName(self, "Select Game EXE", "", "EXE files (*.exe)")
        if exe_path:
            self.exe_path = exe_path
            self.game_dir = os.path.dirname(exe_path)
            self.path_label.setText(f"Selected: {self.exe_path}")
            self.log_output.append(f"📂 Selected: {self.exe_path}")
            self.prefix_btn.setEnabled(True)

    def select_base_prefix(self):
        if not self.exe_path:
            self.log_output.append("❌ Please select an EXE first.")
            return

        base_prefix = QFileDialog.getExistingDirectory(self, "Select Base Wine Prefix")
        if base_prefix:
            self.base_prefix = base_prefix
            self.prefix_label.setText(f"Base Prefix: {self.base_prefix}")
            self.log_output.append("⏳ Creating temp prefix in background...")

            self.prefix_worker = PrefixWorker(self.base_prefix, self.wine_binary, self.game_dir)
            self.prefix_worker.log.connect(self.log_output.append)
            self.prefix_worker.progress.connect(self.log_output.append)
            self.prefix_worker.finished.connect(self.on_prefix_finished)
            self.prefix_worker.start()

    def on_prefix_finished(self, success, temp_prefix):
        if success:
            self.temp_prefix = temp_prefix
            self.check_dxvk_installed()
            self.log_output.append(f"✅ Temp prefix ready at {self.temp_prefix}")
        else:
            self.log_output.append("❌ Failed to create temp prefix.")

    # ---------- Vulkan & DXVK Checks ----------
    def check_vulkan_support(self):
        try:
            result = subprocess.run(["vulkaninfo"], capture_output=True, text=True, timeout=5)
            if "deviceName" in result.stdout:
                self.vulkan_supported = True
                self.vulkan_status.setText("✅ Vulkan Supported")
                self.log_output.append("✅ Vulkan is supported.")
            else:
                self.vulkan_status.setText("❌ Vulkan Not Detected")
        except Exception:
            self.vulkan_status.setText("❌ Vulkan Check Failed")

    def check_dxvk_installed(self):
        if not self.base_prefix:
            return
        system32 = os.path.join(self.base_prefix, "drive_c", "windows", "system32")
        dxvk_files = ["d3d11.dll", "dxgi.dll"]
        self.dxvk_installed = all(os.path.exists(os.path.join(system32, f)) for f in dxvk_files)
        self.log_output.append("✅ DXVK detected." if self.dxvk_installed else "❌ DXVK not found.")

    # ---------- Analyze / Install Dependencies ----------
    def analyze_exe(self):
        if not self.exe_path or not self.temp_prefix:
            self.log_output.append("❌ EXE or Temp Prefix not ready.")
            return
        env = os.environ.copy()
        env["WINEPREFIX"] = self.temp_prefix
        try:
            result = subprocess.run([self.wine_binary, self.exe_path],
                                    env=env,
                                    cwd=self.game_dir,
                                    capture_output=True, text=True, timeout=15)
            output = result.stdout + result.stderr
            self.log_output.append(f"📜 Wine Output:\n{output}")

            missing_dlls = []
            for line in output.splitlines():
                if ".dll" in line.lower() and ("cannot find" in line.lower() or "not found" in line.lower()):
                    for word in line.split():
                        if word.lower().endswith(".dll") and word.lower() not in missing_dlls:
                            missing_dlls.append(word.lower())
            if missing_dlls:
                self.log_output.append(f"❗ Missing DLLs: {', '.join(missing_dlls)}")
            else:
                self.log_output.append("✅ No missing DLLs detected.")
        except subprocess.TimeoutExpired:
            self.log_output.append("⏱️ Wine timed out during analysis.")

    def install_dependencies(self):
        if not self.temp_prefix:
            self.log_output.append("❌ Temp Prefix not ready.")
            return
        env = os.environ.copy()
        env["WINEPREFIX"] = self.temp_prefix
        self.log_output.append("📦 Installing dependencies via winetricks...")
        subprocess.run(["winetricks", "--unattended", "vcrun2015", "dxvk"], env=env)
        self.log_output.append("✅ Dependencies installed.")

    # ---------- Launch Game ----------
    def launch_game(self):
        if not self.exe_path or not self.temp_prefix:
            self.log_output.append("❌ EXE or Temp Prefix not ready.")
            return

        env = os.environ.copy()
        env["WINEPREFIX"] = self.temp_prefix

        if self.vulkan_supported and self.dxvk_installed:
            env["DXVK_LOG_LEVEL"] = "info"
            env["WINEDEBUG"] = "-all"
            env["WINEDLLOVERRIDES"] = "d3d11"

        command = [self.wine_binary, self.exe_path]
        self.log_output.append(f"🎮 Launching {self.exe_path}...")
        subprocess.run(command, env=env, cwd=self.game_dir)
        self.log_output.append("✅ Game exited.")

        self.cleanup_temp_prefix()

    # ---------- Cleanup ----------
    def cleanup_temp_prefix(self):
        if self.temp_prefix and os.path.exists(self.temp_prefix):
            try:
                shutil.rmtree(self.temp_prefix)
                self.log_output.append("✅ Temp Prefix cleaned up.")
            except Exception as e:
                self.log_output.append(f"❌ Error cleaning Temp Prefix: {e}")
            finally:
                self.temp_prefix = ""

    def closeEvent(self, event):
        self.cleanup_temp_prefix()
        event.accept()

# ---------- Main ----------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    launcher = WineLauncher()
    launcher.show()
    sys.exit(app.exec_())
