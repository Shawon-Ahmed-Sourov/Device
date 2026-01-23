
import os, shutil, subprocess
from PyQt5.QtCore import QThread, pyqtSignal

class Prefix(QThread):

    log, done = pyqtSignal(str), pyqtSignal(bool)

    def __init__(self, num: int, exe_path, bprefix_path=None):
        super().__init__()
        self.num, self.exe_path, self.bprefix_path = num, exe_path, bprefix_path


    # --- Internal Utilities( Common Task to reduce program line ) ---


    def _ensure_dirs_exist(self, dirs):
        try   : [os.makedirs(d, exist_ok=True) for d in dirs] ; return True
        except: return False

    def _run_command(self, cmd, env=None, cwd=None):
        try:    return subprocess.run(cmd, check=True, capture_output=True, env=env, cwd=cwd, text=True)
        except Exception as e:    return e

    def _detect_fs(self, path):
        try:
            res = self._run_command(["df", "-T", path])
            return res.stdout.splitlines()[1].split()[1].lower()
        except: return "unknown"

    def _remove_path(self, path):
        try:
            self._run_command(["pkexec", "rm", "-rf", path])
            return True
        except:    return False

    def _is_mounted(self, path):
        result = self._run_command(["mount"])
        if isinstance(result, subprocess.CompletedProcess):    return path in result.stdout
        return False


    # --- Main Thread Logic ---

    def run(self):
        ops = {
            1: (self._create_base_prefix, "\n📂 Creating Base Wine Prefix..."),

            3: (self._create_temp_prefix, "\n⚡ Creating Temporary Overlay Prefix... Please hold on."),
            4: (self._delete_temp_prefix, "\n🗑️ Deleting Temporary Prefix... Please wait.")
        }
        if self.num in ops:
            func, msg = ops[self.num]
            self.log.emit(msg)
            self.done.emit(func())
        else:    self.log.emit("❌ Invalid operation.") ;  self.done.emit(False)


    def _create_base_prefix(self):
        try:
            from pathlib import Path
            prefix_dir = Path(__file__).parent.resolve() / "BasePrefix"
            self.log.emit(f"📂 Creating Wine Base-Prefix at: \n{prefix_dir}")

            os.makedirs(prefix_dir, exist_ok=True)
            
            env = { **os.environ, "WINEPREFIX": str(prefix_dir), "WINEARCH": "win64", "WINEDEBUG": "-all" }
            cmd = "wineboot -i && wine reg add 'HKCU\\Software\\Wine\\Config' /v Version /d win10 /f"
        
            self.log.emit(f"🚀 Running: \n{cmd}")
            subprocess.run(cmd, env=env, shell=True, check=True, capture_output=True )
        
            self.log.emit(f"✅ BasePrefix is Constructed.")
            return True
        except Exception as e:    self.log.emit(f"❌ Error: {e}"); return False

    
    def _delete_temp_prefix(self):

        ovl = os.path.join(self.exe_path, ".wine_temp_noverlay")
        mrg = os.path.join(ovl, "merged")
        
        if not os.path.exists(ovl): return True
        if not self._is_mounted(mrg):    return self._remove_path(ovl)
        
        cmd = f"fusermount -u '{mrg}' || pkexec umount -l '{mrg}' || pkexec umount '{mrg}'; [ -d '{ovl}' ] && pkexec rm -rf '{ovl}'"
        self._run_command(["pkexec", "bash", "-c", cmd])
        
        success = not os.path.exists(ovl)
        self.log.emit("✅ Removed" if success else "❌ Failed")
        return success

    def _create_temp_prefix(self):

        if not (self.exe_path and self.bprefix_path):  self.log.emit("❌ Select EXE and BasePrefix."); return False 

        ovl = os.path.join(self.exe_path, ".wine_temp_noverlay")
        dirs = {k: os.path.join(ovl, k) for k in ["upper", "work", "merged"]}
        if not self._ensure_dirs_exist(dirs.values()): return False

        fs, opts = self._detect_fs(self.exe_path), f"lowerdir={self.bprefix_path},upperdir={dirs['upper']},workdir={dirs['work']}"
        m_map = {
            'ext4': ["pkexec", "mount", "-t", "overlay", "overlay", "-o", opts, dirs['merged']],
            'xfs':  ["pkexec", "mount", "-t", "overlay", "overlay", "-o", opts, dirs['merged']],
            'fuseblk': ["fuse-overlayfs", "-o", opts, dirs['merged']]
        }
        
        cmd = m_map.get(fs)
        if not cmd or self._run_command(cmd).returncode != 0: return False
        return self._init_wine_temp_prefix(dirs["merged"])


    def _init_wine_temp_prefix(self, merged):
        try:
            os.makedirs(os.path.join(merged, "drive_c", "windows"), exist_ok=True)
            env = {**os.environ, "WINEPREFIX": merged, "WINEDEBUG": "-all", "WINEUPDATE": "0"}
            self._run_command(["wine", "wineboot"], env=env, cwd=os.path.dirname(self.exe_path))
            self._run_command(["wine", "reg", "add", "HKCU\\Software\\Wine\\Wine\\Config", "/v", "Version", "/d", "10.0", "/f"], env=env)
            self.log.emit("✅ Wine prefix ready.")
            return True
        except Exception as e:    self.log.emit(f"❌ Init failed: {e}")    ;    return False

