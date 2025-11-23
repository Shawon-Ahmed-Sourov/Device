
import os
import subprocess
from PyQt5.QtCore import QThread, pyqtSignal

class Prefix(QThread):
    log = pyqtSignal(str); done = pyqtSignal(bool)

    def __init__(self, num, exe_path=None, bprefix_path=None):
        super().__init__()
        self.wine = 'wine'
        self.num = num
        self.bprefix_path = bprefix_path
        self.exe_path = exe_path

    def run(self):

        if    self.num == 3:    self.create_temp_prefix()
        elif  self.num == 4:    self.delete_temp_prefix()
        else: self.log.emit("❌ Invalid num value, unable to process."); self.done.emit(False)

    ### Temp Prefix Creation
    def create_temp_prefix(self):

        overlay_dir = self._create_overlay()

        if not overlay_dir:    self.done.emit(False); return
        if not self._initialize_wine_prefix(overlay_dir):    self.done.emit(False); return

        self.done.emit(True)

    def _build_overlay_mount_command(self, lower_dir, overlay_dir):
        return [    'pkexec', 'mount', '-t', 'overlay', 'overlay', '-o',
                    f'lowerdir={lower_dir},upperdir={overlay_dir}/upper,workdir={overlay_dir}/work',
                    os.path.join(overlay_dir, "merged")
            ]

    def _create_overlay(self):

        overlay_dir = os.path.join(self.exe_path, ".wine_temp_noverlay")
        os.makedirs(overlay_dir, exist_ok=True)
        for subdir in ("upper", "work", "merged"):    os.makedirs(os.path.join(overlay_dir, subdir), exist_ok=True)

        lower_dir = self.bprefix_path
        merged_dir = os.path.join(overlay_dir, "merged")
        mount_command = self._build_overlay_mount_command(lower_dir, overlay_dir)

        self.log.emit(f"Mounting: {mount_command}")
        try:
            subprocess.run(mount_command, check=True)
            self.log.emit("✅ Overlay mounted successfully."); return overlay_dir
        except subprocess.CalledProcessError as e:    self.log.emit(f"❌ Overlay setup failed: {e}"); return None

    def _build_wine_env(self, merged_dir):

        return {**os.environ,
                "WINEPREFIX": merged_dir,
                "WINEUPDATE": "0",
                "WINEDEBUG": "-all",
                "WINEARCH": "win64",
                "WINEDLLOVERRIDES": "dll=ignore"
                }

    def _initialize_wine_prefix(self, overlay_dir):
        merged_dir = os.path.join(overlay_dir, "merged")
        os.makedirs(os.path.join(merged_dir, "drive_c", "windows"), exist_ok=True)

        env = self._build_wine_env(merged_dir)
        try:
            winecfg_result = subprocess.run([self.wine, "winecfg"], env=env, cwd=os.path.dirname(self.exe_path), check=True, capture_output=True, text=True)
            for line in winecfg_result.stdout.splitlines():    self.log.emit(f"Winecfg output: {line}")
            for line in winecfg_result.stderr.splitlines():    self.log.emit(f"Winecfg error: {line}")

            reg_result = subprocess.run([self.wine, "reg","add", "HKCU\\Software\\Wine\\Wine\\Config", "/v","Version","/d","10.0","/f"],
                                     env=env, cwd=os.path.dirname(self.exe_path), check=True, capture_output=True, text=True, bufsize=1 )
            for line in reg_result.stdout.splitlines():    self.log.emit(f"✅output_{line}")
            for line in reg_result.stderr.splitlines():    self.log.emit(f"❌error_{line}")

            self.log.emit("✅ Wine prefix initialized with Win10 successfully.")
            return True
        except subprocess.CalledProcessError as e:  self.log.emit(f"❌ Wine prefix initialization failed: {e}"); return False


    ### Temp Prefix Deletion
    def delete_temp_prefix(self):

        overlay_dir = os.path.join(self.exe_path, ".wine_temp_noverlay")
        merged_dir = os.path.join(overlay_dir, "merged")

        if not os.path.exists(overlay_dir):             self.log.emit("ℹ️ No Temp Prefix found."); return
        if not self._is_overlay_mounted(merged_dir):    self.log.emit(f"ℹ️ {merged_dir} is not mounted."); return
        self._unmount_and_delete(merged_dir, overlay_dir)

    def _is_overlay_mounted(self, merged_dir):

        result = subprocess.run(["mount"], check=True, capture_output=True, text=True)
        return merged_dir in result.stdout

    def _unmount_and_delete(self, merged_dir, overlay_dir):

        self.log.emit(f"Unmounting: {merged_dir}\nDeleting: {overlay_dir}")
        command = f'umount "{merged_dir}" && rm -rf "{overlay_dir}"'
        subprocess.run(["pkexec", "bash", "-c", command], check=True, capture_output=True, text=True)
        self.log.emit("✅ Successfully Unmounted and Deleted.\n")
