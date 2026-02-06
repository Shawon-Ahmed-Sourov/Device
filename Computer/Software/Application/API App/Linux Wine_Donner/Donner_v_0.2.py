# Date : 16 OCT 2025
# Flouncher_v_0.2.py
# Approach : Symlink
# Symlinking : pointing BasePrefix, reading Nice, But Writing Changes BasePrefix Configs

import os, sys, shutil, subprocess

from PyQt5.QtWidgets import QApplication, QWidget, QPushButton, QLabel, QVBoxLayout, QFileDialog, QTextEdit

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
        self.optimizations = {
            'fsync': False,
            'mangohub': False,
            'gamemode': False,
            'cpu_governor': False
        }

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
            self.create_temp_prefix()
            self.check_dxvk_installed()

    def create_temp_prefix(self):
        if not self.base_prefix or not self.exe_path:
            self.log_output.append("❌ EXE or Base Prefix not selected.")
            return

        self.temp_prefix = os.path.join(self.game_dir, ".wine_temp")

        # Remove existing temp prefix
        if os.path.exists(self.temp_prefix):
            try:
                if os.path.islink(self.temp_prefix):
                    os.remove(self.temp_prefix)
                else:
                    shutil.rmtree(self.temp_prefix)
                self.log_output.append("✅ Removed old Temp Prefix.")
            except Exception as e:
                self.log_output.append(f"❌ Error removing old Temp Prefix: {e}")
                return

        try:
            # Symlink base prefix to temp prefix
            os.symlink(self.base_prefix, self.temp_prefix)
            self.log_output.append(f"✅ Temp Prefix created at {self.temp_prefix}")

            # Initialize prefix silently
            env = os.environ.copy()
            env["WINEPREFIX"] = self.temp_prefix
            subprocess.run([self.wine_binary, "wineboot", "-u"], env=env, cwd=self.game_dir, check=True)

            # Set Windows version silently
            subprocess.run([self.wine_binary, "reg", "add",
                            "HKEY_CURRENT_USER\\Software\\Wine\\Version",
                            "/ve", "/d", "win10", "/f"],
                           env=env, check=True)
            self.log_output.append("✅ Temp Prefix initialized and set to Windows 10.")
        except Exception as e:
            self.log_output.append(f"❌ Failed to create Temp Prefix: {e}")

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
        # Example: Add any dependencies you need
        subprocess.run(["winetricks", "--unattended", "vcrun2015", "dxvk"], env=env)
        self.log_output.append("✅ Dependencies installed.")

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

        # Cleanup
        self.cleanup()

    def cleanup(self):
        if self.temp_prefix and os.path.exists(self.temp_prefix):
            try:
                shutil.rmtree(self.temp_prefix)
                self.log_output.append("✅ Temp Prefix cleaned up.")
            except Exception as e:
                self.log_output.append(f"❌ Error cleaning Temp Prefix: {e}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    launcher = WineLauncher()
    launcher.show()
    sys.exit(app.exec_())
