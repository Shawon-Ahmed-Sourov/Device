import os, pty, time, queue, shutil, threading, subprocess
from PyQt5.QtCore import QThread, pyqtSignal

# -------------------------
# Common Utility Functions
# -------------------------
def run_command(cmd, capture_output=False, check=True, env=None, cwd=None, text=True):
    try: return subprocess.run(cmd, check=check, capture_output=capture_output, env=env, cwd=cwd, text=text)
    except subprocess.CalledProcessError as e: return e

def ensure_dirs_exist(dirs):
    try: [os.makedirs(d, exist_ok=True) for d in dirs]; return True
    except OSError as e: return f"❌ Directory creation failed: {e}"

def is_mounted(merged):
    try: return merged in run_command(["mount"], capture_output=True).stdout
    except: return False

def remove_path(path):
    try: run_command(["pkexec", "rm", "-rf", path]); return True
    except Exception as e: return f"❌ Remove failed: {e}"

# -------------------------
# Prefix Manager
# -------------------------
class Prefix(QThread):
    log, done = pyqtSignal(str), pyqtSignal(bool)

    def __init__(self, num: int, exe_path, bprefix_path=None, base_dir=None):
        super().__init__()
        self.num, self.exe_path, self.bprefix_path = num, exe_path, bprefix_path
        self.base_dir = base_dir or os.path.dirname(os.path.abspath(__file__))
        self.wine = "wine"

    def run(self):
        ops = { # Map operations to functions and user-friendly messages
            1: (self._create_base_prefix, "\n📂 Creating Base Wine Prefix..."),
            3: (self._create_temp_prefix, "\n⚡ Creating Temporary Overlay Prefix... Please hold on."),
            4: (self._delete_temp_prefix, "\n🗑️ Deleting Temporary Prefix... Please wait.")
        }
        if self.num in ops:
            func, msg = ops[self.num]
            self.log.emit(msg) ; self.done.emit(func())
        else:    self.log.emit("❌ Invalid operation."); self.done.emit(False)

    def _create_base_prefix(self):
        try:
            p_dir = self.bprefix_path or os.path.join(self.base_dir, "BasePrefix")
            os.makedirs(p_dir, exist_ok=True)
            cmd = f'WINEARCH=win64 WINEPREFIX="{p_dir}" wineboot -q &>/dev/null && WINEPREFIX="{p_dir}" wine reg add "HKCU\\Software\\Wine\\Wine\\Config" /v "Version" /d "10.0" /f &>/dev/null'
            res = subprocess.run(cmd, shell=True, capture_output=True)
            self.log.emit(f"✅ Base prefix: {p_dir}" if res.returncode == 0 else f"❌ Error: {res.stderr.decode()}")
            return res.returncode == 0
        except Exception as e: self.log.emit(f"❌ Error: {e}"); return False

    def _delete_temp_prefix(self):
        ovl = os.path.join(self.exe_path, ".wine_temp_noverlay")
        mrg = os.path.join(ovl, "merged")
        if not os.path.exists(ovl): return True
        if not is_mounted(mrg): return remove_path(ovl)
        
        cmd = f"fusermount -u '{mrg}' || pkexec umount -l '{mrg}' || pkexec umount '{mrg}'; [ -d '{ovl}' ] && pkexec rm -rf '{ovl}'"
        run_command(["pkexec", "bash", "-c", cmd])
        success = not os.path.exists(ovl)
        self.log.emit("✅ Removed" if success else "❌ Failed")
        return success

    def _create_temp_prefix(self):
        if not (self.exe_path and self.bprefix_path): return False
        ovl = os.path.join(self.exe_path, ".wine_temp_noverlay")
        dirs = {k: os.path.join(ovl, k) for k in ["upper", "work", "merged"]}
        if not ensure_dirs_exist(dirs.values()): return False

        fs = self._detect_fs(self.exe_path)
        opts = f"lowerdir={self.bprefix_path},upperdir={dirs['upper']},workdir={dirs['work']}"
        m_cmd = ["pkexec", "mount", "-t", "overlay", "overlay", "-o", opts, dirs['merged']] if fs in ['ext4', 'xfs'] else \
                ["fuse-overlayfs", "-o", opts, dirs['merged']] if fs == 'fuseblk' else None
        
        if not m_cmd or run_command(m_cmd).returncode != 0: return False
        return self._init_wine_temp_prefix(dirs["merged"])

    def _detect_fs(self, path):
        try: return run_command(["df", "-T", path], capture_output=True).stdout.splitlines()[1].split()[1].lower()
        except: return "unknown"

    def _init_wine_temp_prefix(self, merged):
        try:
            os.makedirs(os.path.join(merged, "drive_c", "windows"), exist_ok=True)
            env = {**os.environ, "WINEPREFIX": merged, "WINEDEBUG": "-all", "WINEUPDATE": "0"}
            run_command([self.wine, "wineboot"], env=env, cwd=os.path.dirname(self.exe_path))
            run_command([self.wine, "reg", "add", "HKCU\\Software\\Wine\\Wine\\Config", "/v", "Version", "/d", "10.0", "/f"], env=env)
            self.log.emit("✅ Wine prefix ready."); return True
        except Exception as e: self.log.emit(f"❌ Init failed: {e}"); return False

# -------------------------
# Run Analyze Worker
# -------------------------
class RunAnalyze(QThread):
    log, done = pyqtSignal(str), pyqtSignal(bool)

    def __init__(self, exe_path, exe_file, tprefix_path=None, BepInEx_dll=None):
        super().__init__()
        self.wine, self.tprefix, self.dll, self.exe = "wine", tprefix_path, BepInEx_dll, exe_file

    def run(self):
        try:
            cmd, env = self._build_command()
            m_fd, s_fd = pty.openpty()
            proc = subprocess.Popen(cmd, env=env, cwd=os.path.dirname(self.exe), stdin=s_fd, stdout=s_fd, stderr=s_fd, text=True)
            os.close(s_fd)

            while proc.poll() is None:
                try: 
                    line = os.read(m_fd, 1024).decode(errors="ignore")
                    if line: [self.log.emit(l) for l in line.splitlines()]
                except OSError: break
            
            os.close(m_fd)
            self.done.emit(proc.returncode == 0)
        except Exception as e: self.log.emit(f"❌ Run error: {e}"); self.done.emit(False)

    def _build_command(self):
        env = { **os.environ, "WINEPREFIX": self.tprefix_path or "",
                "PYTHONUNBUFFERED": "1", "WINEDEBUG": "-all",

                    # Sync & Memory (The Speed Trio)
                "WINE_NO_ASLR": "1",# Speeds up large asset mapping
                "WINE_LARGE_ADDRESS_AWARE": "1", # Added for stability

                    # Rendering & Shaders
                "vblank_mode": "0", # For Engine fastest assests-loading
                "DXVK_ASYNC": "1",
                "DXVK_STATE_CACHE_WRITETHROUGH": "1",
                "__GL_SHADER_DISK_CACHE": "1",
                "__GL_SHADER_DISK_CACHE_SKIP_CLEANUP": "1",

                    # System & Library Tweaks
                "STAGING_WRITECOPY": "1",
                "STAGING_SHARED_MEMORY": "1",
                "LD_BIND_NOW": "1",
                "MALLOC_CHECK_": "0",
                "WINE_STDOUT_LINE_BUFFERED": "1",
                "WINEDLLOVERRIDES": "winhttp=n,b",
            }

        try:    # Sync Logic
            import resource
            if resource.getrlimit(resource.RLIMIT_NOFILE)[1] >= 65536: env.update({"WINEESYNC": "1", "WINEFSYNC": "1"})
        except: pass

        try:
            gpu = subprocess.check_output(["lspci"], text=True).lower()
            if "nvidia" in gpu:    env["__GL_THREADED_OPTIMIZATIONS"] = "1"
            elif "amd" in gpu or "intel" in gpu:    env["mesa_glthread"] = "true"
        except: pass

        cmd = [ "taskset", "0xffffffff", self.wine ]
        if self.BepInEx_dll : cmd += [ "mono", self.BepInEx_dll ]
        cmd += [self.exe_file]
        return cmd, env

# -------------------------
# Winetricks Launcher
# -------------------------
class InstallDllsWorker(QThread):
    log = pyqtSignal(str)

    def __init__(self, base, wine_cmd="wine"):
        super().__init__(); self.base, self.wine = base, wine_cmd

    def run(self):
        if not shutil.which("winetricks"): return self.log.emit("❌ winetricks missing")
        subprocess.Popen(["winetricks"], env={**os.environ, "WINEPREFIX": self.base})
        self.log.emit(f"✅ Winetricks started for {self.base}")
