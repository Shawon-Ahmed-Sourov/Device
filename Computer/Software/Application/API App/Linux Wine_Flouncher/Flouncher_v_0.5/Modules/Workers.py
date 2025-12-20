import os, pty, time, subprocess
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
import os, pty, time, subprocess, select, fcntl, resource
from PyQt5.QtCore import QThread, pyqtSignal

class RunAnalyze(QThread):
    log, done = pyqtSignal(str), pyqtSignal(bool)

    def __init__(self, exe_path, exe_file, tprefix_path=None, BepInEx_dll=None):
        super().__init__()
        self.wine, self.proc = "wine", None 
        self.tprefix_path, self.BepInEx_dll, self.exe_file = tprefix_path, BepInEx_dll, exe_file

    def run(self):

        self.log.emit("\n⚡ Launch has been Cliked.")
        cmd, env = self._build_command()
        m_fd, s_fd = None, None
        try:
            m_fd, s_fd = pty.openpty()
            # Fast-path: Set non-blocking to keep UI responsive
            fcntl.fcntl(m_fd, fcntl.F_SETFL, fcntl.fcntl(m_fd, fcntl.F_GETFL) | os.O_NONBLOCK)

            self.proc = subprocess.Popen(
                cmd, env=env, cwd=os.path.dirname(self.exe_file),
                stdin=s_fd, stdout=s_fd, stderr=s_fd, preexec_fn=os.setsid, pass_fds=(s_fd,) )

            os.close(s_fd); s_fd = None  # Close slave immediately
            self._monitor_final(m_fd)    # High-speed log capture
            self.done.emit(self.proc.wait() == 0) # wait() reaps the process so it doesn't stay as a 'zombie' in RAM

        except Exception as e:    self.log.emit(f"❌ Error: {str(e)}"); self.done.emit(False)
        finally:
            for fd in (f for f in (s_fd, m_fd) if f is not None):
                try: os.close(fd)
                except: pass

    def _monitor_final(self, m_fd):
        
        acc, last_emit = [], time.time()
        while self.proc.poll() is None or acc: # Loop while process runs OR data remains in buffer
            r, _, _ = select.select([m_fd], [], [], 0.02)    
            if r:
                try:
                    data = os.read(m_fd, 131072).decode(errors="ignore")
                    if data: acc.append(data)
                except (BlockingIOError, OSError):
                  if self.proc.poll() is not None: break

            now = time.time() # UI Batching: Emits every 200ms to keep gaming performance high
            if acc and (now - last_emit > 0.2):
                self.log.emit("".join(acc))
                acc, last_emit = [], now
            
            if self.proc.poll() is not None and not r: break # Instant exit if process is gone and no new data detected
        if acc: self.log.emit("".join(acc))

    def _build_command(self):
        env = { **os.environ, "WINEPREFIX": self.tprefix_path or "",
                "PYTHONUNBUFFERED": "1", "WINEDEBUG": "-all",

                    # Sync & Memory (The Speed Trio)
                "WINE_NO_ASLR": "1",# Speeds up large asset mapping
                "WINE_LARGE_ADDRESS_AWARE": "1", # Added for stability
                "WINE_NO_WRITE_WATCH":"1", # Unity/2D memory managing overhead-reduce

                    # Rendering & Shaders
                "vblank_mode": "0", # For Engine fastest assests-loading
                "DXVK_ASYNC": "1",
                "DXVK_STATE_CACHE":"1", 
                "LIBGL_ALWAYS_SOFTWARE":"0", # not forcing graphics software rendering
                "__GL_SHADER_DISK_CACHE": "1",
                "__GL_SHADER_DISK_CACHE_SKIP_CLEANUP": "1",

                    # System & Library Tweaks
                "STAGING_SHARED_MEMORY": "1",
                "LD_BIND_NOW": "1",
                "MALLOC_CHECK_": "0",

                "WINE_FULLSCREEN_FSR":"0",
                "WINE_STDOUT_LINE_BUFFERED": "1",
                "WINEDLLOVERRIDES": "winhttp=n,b",
                "MONO_GC_PARAMS": "nursery-size=64m,soft-heap-limit=512m"
            }

        try:    # Sync Logic
            import resource
            if resource.getrlimit(resource.RLIMIT_NOFILE)[1] >= 65536:    env.update({ "WINEFSYNC": "1", "WINEESYNC": "1"})
        except: pass

        try:
            gpu = subprocess.check_output(["lspci"], text=True).lower()
            if "nvidia" in gpu :   env.update({"__GL_THREADED_OPTIMIZATIONS": "1", "NGX_ENABLE_DLSS_PRIMARY": "0"})
            if any(x in gpu for x in ["amd", "intel"]) :   env["mesa_glthread"] = "true"
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
