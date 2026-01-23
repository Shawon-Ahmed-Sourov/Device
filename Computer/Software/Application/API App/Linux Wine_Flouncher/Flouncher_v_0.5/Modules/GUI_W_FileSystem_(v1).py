
import os, shutil, subprocess
from PyQt5.QtCore import QThread, pyqtSignal

class Prefix(QThread):

    log, done = pyqtSignal(str), pyqtSignal(bool)

    def __init__(self, num: int, exe_path, bprefix_path=None):
        super().__init__()
        self.num, self.exe_path, self.bprefix_path = num, exe_path, bprefix_path

    def run(self):
        ops = {
            1: (self._create_base_prefix, "\n📂 Creating Base Wine Prefix..."),
            2: (self._delete_prefix, "\n🗑️ Deleting BasePrefix."),
            3: (self._create_temp_prefix, "\n⚡ Creating Temporary NOverlay Prefix... Please hold on."),
            4: (self._delete_prefix, "\n🗑️ Deleting TemPrefix."),
        }
        if self.num in ops:
            func, msg = ops[self.num]
            self.log.emit(msg)
            self.done.emit(func())
        else:    self.log.emit("❌ Invalid Operation.") ;  self.done.emit(False)


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



    def _delete_prefix(self):

        if self.num == 2:  target = str(Path(__file__).parent.resolve() / "BasePrefix")
        else:              target = os.path.join(self.exe_path, ".wine_temp_noverlay")

        if not target or not os.path.exists(target):  self.log.emit("❌ No Directory found.") ; return True
        
        mrg = os.path.join(target, "merged")
        if os.path.exists(mrg) and subprocess.run(["mountpoint", "-q", mrg]).returncode == 0:
            self.log.emit(f"🔗 Unmounting & Deleting: {target}")
            cmd = f"fusermount -u '{mrg}' || umount -l '{mrg}' || umount '{mrg}'; rm -rf '{target}'"
        else:
            self.log.emit(f"🗑️ Deleting: {target}")
            cmd = f"rm -rf '{target}'"

        subprocess.run(["pkexec", "bash", "-c", cmd], capture_output=True)
        success = not os.path.exists(target)
        self.log.emit("✅ Removed successfully." if success else "❌ Failed to remove folder.")
        return success



    def _create_temp_prefix(self):

        if not (self.exe_path and self.bprefix_path):  self.log.emit("❌ Select EXE & B.Prefix."); return False 

        ovl = os.path.join(self.exe_path, ".wine_temp_noverlay")
        dirs = {k: os.path.join(ovl, k) for k in ["upper", "work", "merged"]}
        try : 
            for d in dirs.values(): os.makedirs(d, exist_ok=True)
        except Exception as e: self.log.emit(f"❌ Failed to create directories: {e}"); return False
        try:
            df_proc = subprocess.run( [ "df", "-T", self.exe_path], capture_output=True, text=True, check=True )
            fs = df_proc.stdout.splitlines()[1].split()[1].lower()
        except Exception : fs = "unknown"

        opts = f"lowerdir={self.bprefix_path},upperdir={dirs['upper']},workdir={dirs['work']}"
        m_map = {
            'ext4':    ["pkexec", "mount", "-t", "overlay", "overlay", "-o", opts, dirs['merged']],
            'xfs':     ["pkexec", "mount", "-t", "overlay", "overlay", "-o", opts, dirs['merged']],
            'fuseblk': ["fuse-overlayfs", "-o", opts, dirs['merged']]
        }
        cmd = m_map.get(fs)
        if not cmd : self.log.emit(f"❌ Unsupported filesystem: {fs}") ; return False

        try :    subprocess.run(cmd, check=True, capture_output=True, text=True)
        except Exception as e: self.log.emit(f"❌ Mount failed: {e}") ; return False

        return self._init_wine_temp_prefix(dirs["merged"])


    def _init_wine_temp_prefix(self, merged):
        try:
            os.makedirs(os.path.join(merged, "drive_c", "windows"), exist_ok=True)
            env = {**os.environ, "WINEPREFIX": merged, "WINEDEBUG": "-all", "WINEUPDATE": "0"}
            cwd = os.path.dirname(self.exe_path)

            subprocess.run(["wine", "wineboot"], env=env, cwd=cwd, check=True, capture_output=True)
            subprocess.run(["wine", "reg", "add", "HKCU\\Software\\Wine\\Wine\\Config", "/v", "Version", "/d", "10.0", "/f"], env=env, check=True, capture_output=True)

            self.log.emit("✅ Wine prefix ready.") ; return True
        except Exception as e:  self.log.emit(f"❌ Init failed: {e}") ; return False

