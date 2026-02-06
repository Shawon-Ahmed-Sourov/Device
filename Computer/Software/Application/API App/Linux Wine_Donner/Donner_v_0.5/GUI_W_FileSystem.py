
import os, subprocess
from pathlib import Path
from PyQt5.QtCore import QThread, pyqtSignal

class Prefix(QThread):

    log, done = pyqtSignal(str), pyqtSignal(bool)

    def __init__(self, num: int, exe_path, bprefix_path=None):
        super().__init__()
        self.num, self.exe_path, self.bprefix_path = num, exe_path, bprefix_path

    def run(self):
        ops = {
            1: (self._create_base_prefix, "\n📂 Creating Base Wine Prefix..."),
            2: (self._delete_prefix,      "\n🗑️ Deleting BasePrefix."),
            
            3: (self._create_temp_prefix, "\n⚡ Creating Temporary NOverlay Prefix... Please hold on."),
            4: (self._delete_prefix,      "\n🗑️ Deleting TemPrefix."),
        }
        if  self.num in ops:  func, msg = ops[self.num] ; self.log.emit(msg) ; self.done.emit(func())
        else:    self.log.emit("❌ Invalid Operation.") ; self.done.emit(False)


    def _delete_prefix(self):

        if    self.num == 2:    target = str(Path(__file__).parent.resolve() / "BasePrefix")
        elif  self.num == 4:    target = os.path.join(self.exe_path, ".wine_temp_noverlay")
        if not os.path.exists(target):  self.log.emit("❌ No Directory found.") ; return True
        
        self.log.emit(f"🧹 Cleaning and Deleting: {target}")
        cmd = f"umount -l '{target}'/* 2>/dev/null; rm -rf '{target}'"

        subprocess.run(["pkexec", "bash", "-c", cmd], capture_output=True)
        success = not os.path.exists(target)
        self.log.emit("✅ Removed successfully." if success else "❌ Failed to remove folder.")
        return success



    def _create_temp_prefix(self):

        if not self.bprefix_path:  self.log.emit("❌ Missing BPrefix."); return False

        ovl_root = os.path.join(self.exe_path, ".wine_temp_noverlay")
        paths = {k: os.path.join(ovl_root, k) for k in ["upper", "work", "merged"]}
        for d in paths.values(): os.makedirs(d, exist_ok=True)

        # 2. Mount the Merged( Native Overlay FileSystem ) : Lower (ReadOnly) + Upper (Empty/Changes)
        # Always Update BasePrefix by latest wine : $ WINEPREFIX="$HOME/BasePrefix" wineboot -u
        try:
            opts = f"lowerdir={self.bprefix_path},upperdir={paths['upper']},workdir={paths['work']},noatime"
            cmd = ["pkexec", "mount", "-t", "overlay", "overlay", "-o", opts, paths['merged']]
            subprocess.run(cmd, check=True)
            self.log.emit("✅ Lightweight 📂Prefix Created.\n")
            return True

        except subprocess.CalledProcessError as e:
            self.log.emit(f"❌ UnCreatable: {e.stderr}\n")
            return False


    def _create_base_prefix(self):
        try:
            prefix_dir = Path(__file__).parent.resolve() / "BasePrefix"
            self.log.emit(f"⚡ Initializing: {prefix_dir}")
            os.makedirs(prefix_dir, exist_ok=True)

            # Optimization: Disable menu building and set arch/prefix
            env = { **os.environ,  "WINEPREFIX": str(prefix_dir), 
                    "WINEARCH": "win64", "WINEDEBUG": "-all", "WINEDLLOVERRIDES": "winemenubuilder.exe=d" }

            self.log.emit("⚡Building core files...")
            subprocess.run(["wineboot", "-i"], env=env, check=True, capture_output=True)

            self.log.emit("⚙️ Setting registry to Win10...")
            reg_cmd = ["wine", "reg","add", "HKCU\\Software\\Wine\\Config","/v","Version","/d", "win10","/f"]
            subprocess.run(reg_cmd, env=env, check=True, capture_output=True)

            self.log.emit("✅ BasePrefix Ready.\n")
            return True
        except Exception as e:  self.log.emit(f"❌ Error: {str(e)}") ; return False


