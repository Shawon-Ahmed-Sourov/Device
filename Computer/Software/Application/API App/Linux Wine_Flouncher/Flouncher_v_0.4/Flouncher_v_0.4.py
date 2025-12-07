# Date : 26 OCT 2025
# Flouncher_v_0.4.py

# sudo apt install python3 python3-pyqt5

# Approach : overlay union
# success : (Fast)Linux ext4 FileSystem, (Slower) non-linux drive-NTFS

# Code is shrinked without compromising functionality,function,feautures, GUI modern looks
# Always Active : Select Base Prefix

# Temprefix : Fast-Delete well by sudo, unfreeze Creates Fast configuration wine_temp_overlay
# Temprefix : Disable untill selected Both BasePrefix +S/G.exe

# LogBox shows : sysVulkan-Support, Path-Selected-BPref& G/Soft.exe 
# Create Prefix fast( GUI !Freezes ), faster

# Tried Fixing OS.All.stuck by Launched G/Soft.exe
# Install dlls into BPrefix : by only Winetricks( But Not Forcely)
# Analyze Exe : using Temprefix running only 90sec

import os, sys, time, queue, shutil, threading, subprocess
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QFrame
from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QPushButton, QCheckBox, QFileDialog, QTextEdit

# ---------------- Worker Threads ---------------- #

class InstallDllsWorker(QThread):

    log = pyqtSignal(str)

    def __init__(self, base):    super().__init__(); self.base = base

    def run(self):
        if shutil.which("winetricks") is None:
            self.log.emit("❌ Please may install winetricks."); return

        self._start_winetricks()

    def _start_winetricks(self):
        try:
            self.log.emit("⚡ Opening Winetricks GUI...")
            subprocess.Popen(["winetricks"], env={"WINEPREFIX": self.base, **os.environ})
            self.log.emit(f"✅ Terminal-Command: $ WINEPREFIX={self.base} winetricks")
        except Exception as e:    self.log.emit(f"❌ Failed to start winetricks: {e}")


# SetUp-isolated WinePrefix By Overlay Approach
class TemprefixWorker(QThread):
    log = pyqtSignal(str); done = pyqtSignal(bool)

    def __init__(self, exe, base, temp, wine):
        super().__init__()
        self.base, self.temp, self.wine, self.exe = base, temp, wine, exe

    def run(self):
        u, w, m = [os.path.join(self.temp, p) for p in ("upper", "work", "merged")]
        self._prepare_dirs(u, w, m)
        fs = self._detect_fs(self.temp)
        self._create_tprefix(u, w, m, fs)
        self._initialize_tprefix(m)

    def _prepare_dirs(self, u, w, m):

        try:    [os.makedirs(d, exist_ok=True) for d in (u, w, m)]
        except OSError as e:    self.log.emit(f"❌ Directory couldn't prepare: {e}"); self.done.emit(False)

    def _detect_fs(self, path):
        try:
            out = subprocess.run(["df", "-T", path], capture_output=True, text=True, check=True).stdout
            return out.splitlines()[1].split()[1].lower()
        except subprocess.CalledProcessError:    self.log.emit(f"❌ Error detecting filesystem"); return "unknown"

    def _create_tprefix(self, u, w, m, fs):
        try:
            if fs in ("ext4", "btrfs", "xfs"):
                cmd = ["pkexec", "mount", "-t", "overlay", "overlay", 
                       "-o", f"lowerdir={self.base},upperdir={u},workdir={w}", m]
                fs_type = "native OverlayFS"
            else:
                cmd = ["fuse-overlayfs", "-o", f"lowerdir={self.base},upperdir={u},workdir={w}", m]
                fs_type = "fuse-overlayfs"
    
            self.log.emit(f"⚡ Using {fs_type} on {fs}.") ; subprocess.run(cmd, check=True)
            self.log.emit(f"✅ TPrefix created at {m}")

        except subprocess.CalledProcessError as e: self.log.emit(f"❌ Overlay couldn't mount: {e}"); self.done.emit(False)

    def _initialize_tprefix(self, m):
        try:
            env = {**os.environ, "WINEPREFIX": m, "WINEDLLOVERRIDES": "dll=ignore", "WINEDEBUG": "-all"}
            os.makedirs(os.path.join(m, "drive_c", "windows"), exist_ok=True)
            if not os.path.exists(os.path.join(m, "user.reg")):
                subprocess.run([self.wine, "wineboot", "-u"], env=env, cwd=os.path.dirname(self.exe), check=True)
            self.log.emit("✅ TPrefix Initialized with Windows 10."); self.done.emit(True)
        except subprocess.CalledProcessError as e:    self.log.emit(f"❌ TPrefix couldn't setup: {e}"); self.done.emit(False)


class DeleteTempPrefixWorker(QThread):
    log = pyqtSignal(str)

    def __init__(self, temp):    super().__init__(); self.temp = temp

    def run(self):
        if not os.path.exists(self.temp):    self.log.emit("ℹ️ No Temp Prefix found."); return
        self._delete_temp_prefix()

    def _delete_temp_prefix(self):
        m = os.path.join(self.temp, "merged")
        try:
            for cmd in (["fusermount", "-u", m], ["pkexec", "umount", "-l", m]):
                subprocess.run(cmd, check=False)
            time.sleep(0.3)
            self._execute_deletion()
        except Exception as e:    self.log.emit(f"❌ Deletion failed: {e}")

    def _execute_deletion(self):
        try:
            self.log.emit("⚡ Using Pkexec for deletion...")
            subprocess.run(["pkexec", "rm", "-rf", self.temp], check=True)
            self.log.emit("✅ Temp Prefix deleted via Pkexec.")
        except Exception:    self.log.emit("❌ Deletion failed.")


class AnalyzeAndRunExeWorker(QThread):
    log = pyqtSignal(str)
    started_signal = pyqtSignal(str)

    def __init__(self, exe, temp, wine):
        super().__init__()

        self.temp = temp ; self.exe = exe ; self.wine = wine

    def run(self):

        m = os.path.join(self.temp, "merged")
        env = self._setup_env(m)
        self._launch_exe(env, m)

    def _setup_env(self, m):
        return {
            **os.environ,
            "WINEPREFIX": m,
            "WINE_FULLSCREEN": "0",
            "WINEDEBUG": "+timestamp,+warn",
            "WINE_ALLOW_LARGE_ALLOCS": "1",
            "WINEESYNC": "1",
            "WINEFSYNC": "1",
            "WINEASYNC": "0",
        }

    def _launch_exe(self, env, m):
        cmd = [self.wine, self.exe]
        self.started_signal.emit(f"🚀 Launching EXE:\n$ {' '.join([f'{k}={v}' for k, v in env.items() if k.startswith('WINE')])} {' '.join(cmd)}")

        try:
            proc = subprocess.Popen(cmd, env=env, cwd=os.path.dirname(self.exe),
                                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            self._monitor_proc_output(proc)
        except Exception as e:    self.log.emit(f"❌ Launch failed: {e}")


    def _monitor_proc_output(self, proc):
        q = queue.Queue()
        def reader_thread():
            for line in iter(proc.stdout.readline, ''):
                q.put(line.strip())
            proc.stdout.close()

        threading.Thread(target=reader_thread, daemon=True).start()

        missing_dlls = set()
        while proc.poll() is None or not q.empty():
            try:
                line = q.get(timeout=0.2)
                if line:
                    self.log.emit(line)
                    if ".dll" in line.lower() and ("cannot" in line.lower() or "not found" in line.lower()):
                        missing_dlls.add(line.split()[0].lower())
            except queue.Empty:    pass

        proc.wait()
        self._log_missing_dlls(missing_dlls, proc)

    def _log_missing_dlls(self, missing_dlls, proc):
        with open(os.path.join(os.path.dirname(self.exe), "Analyzable-logs.txt"), "w") as f:f.write("\n".join(missing_dlls))

        if missing_dlls:    self.log.emit(f"❗ Missing DLLs: {', '.join(sorted(missing_dlls))}")
        else:    self.log.emit("✅ No missing DLLs detected.")

        self.log.emit("✅ Execution finished." if proc.returncode == 0 else "⚠️ EXE exited with error.")


# ---------------- Main GUI ---------------- #

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


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = WineLauncher()
    w.show()
    sys.exit(app.exec_())
