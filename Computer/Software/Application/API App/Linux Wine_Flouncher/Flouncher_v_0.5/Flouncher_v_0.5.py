# Date : 5 Dec 2025
import os, sys, time, queue, shutil, threading, subprocess
from PyQt5.QtCore import Qt, QThread, pyqtSignal

from PyQt5.QtWidgets import QWidget, QLabel, QFrame, QMainWindow, QApplication, QHBoxLayout, QVBoxLayout
from PyQt5.QtWidgets import QComboBox, QCheckBox, QTextEdit, QFileDialog, QPushButton, QSpacerItem, QSizePolicy

# -------------------------
# Common Utility Functions
# -------------------------
def run_command(cmd, capture_output=False, check=True, env=None, cwd=None, text=True):
    try:
        return subprocess.run(cmd, check=check, capture_output=capture_output, env=env, cwd=cwd, text=text)
    except subprocess.CalledProcessError as e:    return e


def ensure_dirs_exist(dirs):
    """Ensure all directories in the given list exist."""
    try:
        [os.makedirs(d, exist_ok=True) for d in dirs]
        return True
    except OSError as e:    return f"❌ Directory creation failed: {e}"

def is_mounted(merged):
    """Check if a directory is mounted."""
    try:
        return merged in run_command(["mount"], capture_output=True, text=True).stdout
    except Exception:    return False

def remove_path(path):
    """Safely remove a path with elevated privileges."""
    try:
        run_command(["pkexec", "rm", "-rf", path])
        return True
    except Exception as e:    return f"❌ Remove failed: {e}"

# -------------------------
# Prefix Manager (Refactored)
# -------------------------

class Prefix(QThread):

    log = pyqtSignal(str) ; done = pyqtSignal(bool)

    def __init__(self, num: int, exe_path, bprefix_path=None):
        super().__init__()
        self.wine = "wine"
        self.num = num
        self.exe_path = exe_path ; self.bprefix_path = bprefix_path

    def run(self):
        try:
            if   self.num == 3:    self.done.emit(self._create_temp_prefix())
            elif self.num == 4:    self.done.emit(self._delete_temp_prefix())
            else:    self.log.emit("❌ Invalid operation number.") ; self.done.emit(False)
        except Exception as e:    self.log.emit(f"❌ Prefix thread error: {e}") ; self.done.emit(False)

    def _delete_temp_prefix(self):
        """Delete the temporary Wine prefix."""
        overlay_dir = os.path.join(self.exe_path, ".wine_temp_noverlay")
        merged = os.path.join(overlay_dir, "merged")

        if not os.path.exists(overlay_dir):    self.log.emit("ℹ️ No prefix found") ; return True
        if not is_mounted(merged):    return remove_path(overlay_dir)
        return self._unmount_remove(merged, overlay_dir)

    def _unmount_remove(self, merged, overlay_dir):
        """Unmount and remove overlay directory with a single password prompt."""
        try:
            # Quote paths properly to handle spaces
            merged_quoted = f'"{merged}"'
            overlay_dir_quoted = f'"{overlay_dir}"'

            # Combine unmount and removal commands into one single bash command
            unmount_and_remove_cmd = f"""
            fusermount -u {merged_quoted} || pkexec umount -l {merged_quoted} || pkexec umount {merged_quoted}
            [ ! -d {overlay_dir_quoted} ] && echo "Directory already removed." || pkexec rm -rf {overlay_dir_quoted}
            """
            # Log the action
            self.log.emit("Attempting to unmount and delete overlay directory...")

            # Run the combined command with pkexec
            run_command(["pkexec", "bash", "-c", unmount_and_remove_cmd], capture_output=True, text=True)

            # Check if the overlay directory is removed
            if not os.path.exists(overlay_dir):    self.log.emit("✅ Overlay Directory removed.") ; return True
            else:    self.log.emit(f"❌ Failed to remove Directory: {overlay_dir}")				  ; return False

        except Exception as e:    self.log.emit(f"⚠️ Error while Unmounting or Deletion: {e}")    ; return False



    def _create_temp_prefix(self):
        """Create a temporary Wine prefix."""
        if not self.exe_path or not self.bprefix_path: self.log.emit("❌ No Path of exe or BPrefix."); return False

        overlay_dir = os.path.join(self.exe_path, ".wine_temp_noverlay")
        dirs = {p: os.path.join(overlay_dir, p) for p in ("upper", "work", "merged")}

        if not ensure_dirs_exist(dirs.values()): self.log.emit(f"❌ Couldn't prepare overlay dirs.") ; return False

        fs_type = self._detect_fs(self.exe_path)

        if not self._mount_overlay(fs_type, dirs["merged"], overlay_dir):    return False
        return self._init_wine_temp_prefix(dirs["merged"])

    def _detect_fs(self, exe_path):
        """Detect filesystem type with error handling."""
        try:
            out = run_command(["df", "-T", exe_path], capture_output=True, text=True, check=True).stdout
            fs_type = out.splitlines()[1].split()[1].lower()
            self.log.emit(f"Detected Filesystem: {fs_type}")
            return fs_type
        except subprocess.CalledProcessError as e: self.log.emit(f"❌ Unable to detect filesystem: {e}") ; return "unknown"

    def _mount_overlay(self, fs_type, merged, overlay_dir):
        """Mount the overlay filesystem ensuring the base prefix is remain pure & read-only."""
        lower = self.bprefix_path  # base Wine prefix (read-only)
        mount_cmd = []

        if fs_type in ["ext4", "xfs"]:  # Using pkexec to mount with overlay
            mount_cmd = ["pkexec", "mount", "-t", "overlay", "overlay",   "-o", f"lowerdir={lower},upperdir={overlay_dir}/upper,workdir={overlay_dir}/work", merged]
        elif fs_type == "fuseblk":  # Using fuse-overlayfs for fuse filesystems
            mount_cmd = ["fuse-overlayfs", "-o", f"lowerdir={lower},upperdir={overlay_dir}/upper,workdir={overlay_dir}/work", merged]
        else:    self.log.emit(f"❌ Unsupported filesystem type: {fs_type}") ; return False

        try:    run_command(mount_cmd) ; return True
        except Exception as e:    self.log.emit(f"❌ Mount failed: {e}") ; return False

    def _init_wine_temp_prefix(self, merged):
        """Prepare the merged directories and initialize the Wine prefix."""
        try:
            # Step 1: Prepare the directories
            os.makedirs(os.path.join(merged, "drive_c", "windows"), exist_ok=True)

            # Step 2: Set up the Wine environment
            env = {**os.environ, "WINEPREFIX": merged, "WINEDEBUG": "-all", "WINEUPDATE": "0", "WINEDLLOVERRIDES": "dll=ignore", "WINEPOLICY": "1" }

            # Step 3: Initialize the Wine prefix
            self.log.emit("⚡ Initializing Wine Prefix...")
            run_command([self.wine, "winecfg"], env=env, cwd=os.path.dirname(self.exe_path), check=True)

            # Step 4: Check for the Wine version in the registry
            reg_check = run_command([self.wine, "reg", "query", "HKCU\\Software\\Wine\\Wine\\Config", "/v", "Version"], env=env, capture_output=True)
            if "Version" not in getattr(reg_check, "stdout", ""):
                run_command([self.wine, "reg", "add", "HKCU\\Software\\Wine\\Wine\\Config", "/v", "Version", "/d", "10.0", "/f"], env=env)

            self.log.emit("✅ Wine prefix ready (Win10).")
            return True
            
        except OSError as e:    self.log.emit(f"❌ Un-Preparable merged dirs: {e}")
        except Exception as e:    self.log.emit(f"❌ Wine init Failed: {e}")
        return False

# -------------------------
# Run Analyze Worker (Refactored)
# -------------------------

class RunAnalyze(QThread):

    log = pyqtSignal(str) ; done = pyqtSignal(bool)

    def __init__(self, exe_path, exe_file, tprefix_path=None, BepInEx_dll=None):
        super().__init__()
        self.tprefix_path = tprefix_path
        self.wine = "wine" ; self.BepInExEx_dll = BepInEx_dll ; self.exe_file = exe_file

    def run(self):
        try:
            cmd, env = self._build_command()
            self._launch_exe(cmd, env)
        except Exception as e:    self.log.emit(f"❌ Run error: {e}"); self.done.emit(False)

    def _build_command(self):
        
        env = {**os.environ, "WINEPREFIX": self.tprefix_path or "", "WINE_FULLSCREEN": "0", "WINEDEBUG": "+timestamp,+warn", "WINE_ALLOW_LARGE_ALLOCS": "1", "WINEESYNC": "1", "WINEFSYNC": "1", "WINEASYNC": "0"}

        cmd = [self.wine] # Method name : Progmatically List-Based  shell-command-construction.
        if self.BepInExEx_dll:    cmd += ["mono", self.BepInExEx_dll]
        cmd += [self.exe_file]
        return cmd, env

    def _launch_exe(self, cmd, env):
        """Launch the EXE."""
        self.log.emit(f"🚀 Launching EXE: {' '.join(cmd)}")
        try:
            proc = subprocess.Popen(cmd, env=env, cwd=os.path.dirname(self.exe_file), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            self._monitor_proc(proc)
        except Exception as e:    self.log.emit(f"❌ Launch failed: {e}"); self.done.emit(False)

    def _monitor_proc(self, proc):
        """Monitor the process and handle output."""
        q = queue.Queue()
        threading.Thread(target=lambda: [q.put(line.rstrip()) for line in iter(proc.stdout.readline, '')] and proc.stdout.close(), daemon=True).start()
        missing = set()
        while proc.poll() is None or not q.empty():
            try:
                line = q.get(timeout=0.1)
                if not line:    continue
                self.log.emit(line)
                if ".dll" in line.lower() and any(x in line.lower() for x in ("not found", "cannot", "error")):
                    missing.add(line.split()[0].lower())
            except queue.Empty:    pass

        if missing:
            with open(os.path.join(os.path.dirname(self.exe_file), "Analyzable-logs.txt"), "w") as f:
                f.write("\n".join(sorted(missing)))
            self.log.emit(f"❗ Missing DLLs: {', '.join(sorted(missing))}")
        else:    self.log.emit("✅ No missing DLLs detected.")
        self.done.emit(proc.returncode == 0)

# -------------------------
# GUI Class for PyQt
# -------------------------

class WineLauncher(QWidget):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Wine EXE Launcher")
        self.resize(920, 520)
        self.wine, self.mono = "wine", "mono"
        self.bprefix_path, self.tprefix_path = None, None
        self.exe_file, self.exe_path, self.BepInEx_path = None, None, None
        self.init_ui()

    def sep(self):    line = QFrame(); line.setFrameShape(QFrame.HLine); line.setFrameShadow(QFrame.Sunken); return line

    def row(self, *widgets):
        layout = QHBoxLayout()
        for widget in widgets:    layout.addWidget(widget)
        return layout

    def create_button(self, label, fn, enabled=True):    return QPushButton(label, clicked=fn, enabled=enabled)
    def create_combo_box(self, items):    combo = QComboBox(self) ; combo.addItems(items) ; return combo
    def create_checkbox(self, label) :    return QCheckBox(label)
    def create_text_edit(self):    		  log = QTextEdit(readOnly=True) ; return log

    def create_checkbox_group(self):
        chk_v = QVBoxLayout()

        checkboxes = [
            self.create_checkbox("Wine"),
            self.create_checkbox("Vulkan"),
            self.create_checkbox("DXVK"),
            self.create_checkbox("VKD3D"),
            self.create_checkbox("Gamemode")
        ]
        for checkbox in checkboxes:
            chk_v.addWidget(checkbox) ; checkbox.stateChanged.connect(self.on_checkbox_state_changed)

        chk_v.setContentsMargins(1, 1, 1, 1)
        return chk_v

    #--------------------------------------------------------------------------------------------------------------------

    def init_ui(self):
        v = QVBoxLayout()

        # Create buttons
        self.b_selbase = self.create_button("Select The BasePrefix", self.sel_bprefix)
        self.b_exe = self.create_button("Select The G-Soft.exe", self.sel_exe)
        self.b_run = self.create_button("Launch and Analyze", self.launchan)

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
        log_h = QHBoxLayout() ; chk_v = self.create_checkbox_group()

        self.log = self.create_text_edit()

        log_h.addWidget(self.log, 1) ; log_h.addLayout(chk_v, 0)

        v.addLayout(log_h)

        self.setLayout(v)

    # GUI Part Done , Now For Connecting Methods Definition : --------------------------------------------------------------

    def sel_bprefix(self):

        self.bprefix_path = QFileDialog.getExistingDirectory(self, "Select Base Prefix Directory")
        if not self.bprefix_path:    self.log.append("No BasePrefix Directory selected.")
        else:  self.log.append(f"📂 Base Prefix selected: {self.bprefix_path}\n")


    def sel_exe(self):
        exe_file, _ = QFileDialog.getOpenFileName(self, "Select G/Soft.exe", "", "Executable Files (*.exe)")
    
        if not exe_file:    self.log.append("❌ No executable selected.")  ;  return
        else:
            self.exe_file = exe_file
            self.log.append(f"💻 Executable selected: {self.exe_file}\n")

            self.exe_path = os.path.dirname(exe_file)
            self.log.append(f"📂 Executable path: {self.exe_path}")

            self.tprefix_path = os.path.join(self.exe_path, ".wine_temp_noverlay", "merged")
            if not self.tprefix_path:    self.log.append(f"No Prefix Existing.")
            else:    					 self.log.append(f"✅ Existing Prefix : {self.tprefix_path}")
            
            for root, dirs, files in os.walk(self.exe_path):
                if "BepInEx.dll" in files:    self.BepInEx_path = os.path.join(root, "BepInEx.dll"); break
            if self.BepInEx_path:    self.log.append(f"✅ BepInEx.dll found at: {self.BepInEx_path}")


    def on_modify_temp_changed(self, index):
        temp_action = self.modify_temp.itemText(index)
        self.log.append(f"\n\nTemp Prefix option selected: {temp_action}")
        
        if temp_action == "Create":
            self.log.append("Starting Wine Prefix creation...")
            self.worker_thread = Prefix(num=3, exe_path=self.exe_path, bprefix_path=self.bprefix_path)
            self.worker_thread.log.connect(self.log.append)
            self.worker_thread.done.connect(lambda success: self.log.append("✅ Wine prefix created successfully!" if success else "❌ WPrefix creation failed."))
            self.worker_thread.start()

        elif temp_action == "Delete":
            self.log.append("Starting Wine Prefix Deletion...")
            self.worker_thread = Prefix(num=4, exe_path=self.exe_path)
            self.worker_thread.log.connect(self.log.append)
            self.worker_thread.done.connect(lambda success: self.log.append("✅ Wine prefix deleted successfully!" if success else "❌ WPrefix deletion failed."))
            self.worker_thread.start()

    def launchan(self):
        self.log.append("Launch clicked")
    
        if not self.exe_file:    self.log.append("❌ Please select an executable file.")
        else:
            self.worker_thread = RunAnalyze(self.exe_path, self.exe_file, self.tprefix_path)
            self.worker_thread.log.connect(self.log.append)
            self.worker_thread.done.connect(lambda success: self.log.append("✅ Program Closed successfully!" if success else "❌ Program Couldn't Closed."))
            self.worker_thread.start()

              #------- Un Working Functions -------

    def on_resolution_changed(self, index):
        selected_option = self.resolution.itemText(index)
        self.log.append(f"Resolution option selected: {selected_option}")

    def on_checkbox_state_changed(self, state):
        sender = self.sender()
        checkbox_label = sender.text()
        if state == Qt.Checked:    self.log.append(f"{checkbox_label} is enabled.")
        else:					   self.log.append(f"{checkbox_label} is disabled.")

    def on_modify_base_changed(self, index):
        base_option = self.modify_base.itemText(index)
        self.log.append(f"Base Prefix option selected: {base_option}")
        if base_option == "Delete":    self.log.append("Working On Deleting Existing BasePrefix")
        elif base_option == "Create":  self.log.append("Working On Creating BasePrefix")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = WineLauncher()
    window.show()
    sys.exit(app.exec_())  # This should be called to start the event loop
