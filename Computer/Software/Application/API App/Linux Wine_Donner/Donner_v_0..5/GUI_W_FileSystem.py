
import os, shlex, subprocess
from pathlib import Path
from PyQt5.QtCore import QThread, pyqtSignal

class Prefix(QThread):
    log, done = pyqtSignal(str), pyqtSignal(bool)

    def __init__(self, num: int, exe_path, bprefix_path=None):
        super().__init__()
        self.num, self.exe_path, self.bprefix_path = num, exe_path, bprefix_path
        self.base_dir = Path(__file__).parent.resolve() / "BasePrefix"
        self.temp_dir = Path(exe_path) / ".wine_temp_noverlay" if exe_path else None

    def run(self):
        ops = {
            1: (self._create_base_prefix, "\n📂 Creating Base Wine Prefix..."),
            2: (self._delete_prefix,      "\n🗑️ Deleting BasePrefix."),
            3: (self._create_temp_prefix, "\n⚡ Creating Temporary Prefix..."),
            4: (self._delete_prefix,      "\n🗑️ Deleting Temporary Prefix."),
        }
        if self.num in ops:
              func, msg = ops[self.num]
              self.log.emit(msg) ; self.done.emit(func())
        else: self.log.emit("❌ Invalid Operation."); self.done.emit(False)


    def _delete_prefix(self):

        target = self.base_dir if self.num == 2 else self.temp_dir
        if not target or not target.exists():
            self.log.emit("❌ No Directory found."); return True

        self.log.emit(f"🧹 Cleaning: {target}")
        t_q = shlex.quote(str(target))
        merged_q = shlex.quote(str(target / "merged"))
        
        cmd = f"umount -l {merged_q} 2>/dev/null; rm -rf {t_q}"
        subprocess.run(["pkexec", "bash", "-c", cmd])
        
        success = not target.exists()
        self.log.emit("✅ Removed." if success else "❌ Removal failed.")
        return success


    def _create_temp_prefix(self):

        if not self.bprefix_path or not self.temp_dir:
            self.log.emit("❌ Missing Path Info."); return False

        paths = {k: self.temp_dir / k for k in ["upper", "work", "merged"]}
        for d in paths.values(): d.mkdir(parents=True, exist_ok=True)

        try:
            opts = f"lowerdir={self.bprefix_path},upperdir={paths['upper']},workdir={paths['work']},noatime"
            cmd = ["pkexec", "mount", "-t", "overlay", "overlay", "-o", opts, str(paths['merged'])]
            subprocess.run(cmd, check=True, capture_output=True)
            self.log.emit("✅ Lightweight Prefix Created.\n")
            return True
        except subprocess.CalledProcessError as e:
            err = e.stderr.decode().strip()
            self.log.emit(f"❌ Mount Error: {err}\n"); return False

    def _create_base_prefix(self):
        try:
            self.log.emit(f"⏳ Initializing: {self.base_dir}")
            self.base_dir.mkdir(parents=True, exist_ok=True)
        
            target = str(self.base_dir.resolve())    # Abs_path preventin Wine getting lost
            env = {**os.environ, "WINEPREFIX": target, "WINEARCH": "win64", "WINEDEBUG": "-all"}

            self.log.emit("⚙️ Building core files...")
            subprocess.run(["wineboot", "-u"], env=env, check=True, capture_output=True)
            subprocess.run(["wineserver", "-w"], env=env, check=True)

            self.log.emit("✅ Base-Prefix Created.\n")
            return True

        except Exception as e:  self.log.emit(f"❌ Error: {str(e)}") ; return False

