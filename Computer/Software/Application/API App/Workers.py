import os, time, subprocess
from PyQt5.QtCore import QThread, pyqtSignal

class CJob:
    def __init__(self, num, path, obj_name):
        self.num = num 
        self.path = path ; self.obj_name = obj_name

    def analyze(self):
        """ Logically Analyze 'Obj_name', on given path( import OS ) """
        full_path = os.path.join(self.path, self.obj_name)

        if   self.num == 0 :    return os.path.isdir(full_path)
        elif self.num == 1 :    return os.path.isfile(full_path)


class Prefix(QThread):
    log = pyqtSignal(str) ; done = pyqtSignal(bool)

    def __init__(self, num, exe_path=None, bprefix_path=None):
        super().__init__()
        self.wine = "wine" ; self.num = num
        self.bprefix_path = bprefix_path
        self.exe_path = exe_path

    def run(self):
        if   self.num == 3:    self.create_temp_prefix()
        elif self.num == 4:    self.delete_temp_prefix()
        else:    self.log.emit("❌ No Prefix Action Taken.") ; self.done.emit(False)



    ### Temp Prefix Creation
    def create_temp_prefix(self):

        overlay_dir = self._create_overlay()
        if not overlay_dir:    self.done.emit(False); return
        if not self._initialize_wine_prefix(overlay_dir):    self.done.emit(False); return
        self.done.emit(True)

    def _create_overlay(self):

        overlay_dir = os.path.join(self.exe_path, ".wine_temp_noverlay")
        os.makedirs(overlay_dir, exist_ok=True)

        for subdir in ("upper", "work", "merged"):    os.makedirs(os.path.join(overlay_dir, subdir), exist_ok=True)

        lower_dir = self.bprefix_path ; merged_dir = os.path.join(overlay_dir, "merged")

        mount_command = [    'pkexec', 'mount', '-t', 'overlay', 'overlay', '-o',
                        f'lowerdir={lower_dir},upperdir={overlay_dir}/upper,workdir={overlay_dir}/work',
                        os.path.join(overlay_dir, "merged")    ]

        self.log.emit(f"Mounting: {mount_command}")
        try:    subprocess.run(mount_command, check=True); self.log.emit("✅ Overlay Mounted."); return overlay_dir
        except subprocess.CalledProcessError as e:    self.log.emit(f"❌ Overlay setup failed: {e}") ; return None

    def _initialize_wine_prefix(self, overlay_dir):

        merged_dir = os.path.join(overlay_dir, "merged")
        wine_prefix_dir = os.path.join(merged_dir, "drive_c", "windows", "system32")

        if not os.path.exists(wine_prefix_dir):    os.makedirs(os.path.join(merged_dir, "drive_c", "windows"), exist_ok=True)

        env = {**os.environ, "WINEPREFIX": merged_dir, "WINEUPDATE": "0", "WINEDEBUG": "-all", "WINEARCH": "win64", "WINEDLLOVERRIDES": "dll=ignore"}

        try:
            if not os.path.exists(wine_prefix_dir):    subprocess.run([self.wine, "winecfg"], env=env, cwd=os.path.dirname(self.exe_path), check=True)

            wine_version_check = subprocess.run(    [ self.wine, "reg", "query", "HKCU\\Software\\Wine\\Wine\\Config", "/v", "Version"],
                env=env, cwd=os.path.dirname(self.exe_path), capture_output=True, text=True    )

            if "Version" not in wine_version_check.stdout:
                subprocess.run(    [self.wine, "reg", "add", "HKCU\\Software\\Wine\\Wine\\Config", "/v", "Version", "/d", "10.0", "/f"],
                    env=env, cwd=os.path.dirname(self.exe_path), check=True    )

            self.log.emit("✅ Windows set to Win10 in Wine prefix.")
            return True
        except subprocess.CalledProcessError as e:  self.log.emit(f"❌ Couldn't Initializable WPrefix: {e}"); return False



    ### Temp Prefix Deletion
    def delete_temp_prefix(self):

        overlay_dir = os.path.join(self.exe_path, ".wine_temp_noverlay")
        merged_dir = os.path.join(overlay_dir, "merged")

        if not os.path.exists(overlay_dir):    self.log.emit("ℹ️ No Temp Prefix found."); return

        if not self._is_overlay_mounted(merged_dir):    self.log.emit(f"ℹ️ Overlay not mounted: {merged_dir}."); return

        self._unmount_and_delete(merged_dir, overlay_dir)


    def _is_overlay_mounted(self, merged_dir):
        result = subprocess.run(["mount"], check=True, capture_output=True, text=True)
        return merged_dir in result.stdout

    def _unmount_and_delete(self, merged_dir, overlay_dir):
        self.log.emit(f"Unmounting: {merged_dir}\nDeleting: {overlay_dir}")


        try:
            self.log.emit("Only Deleting by unmounting.")
            command = f'umount "{merged_dir}" && rm -rf "{overlay_dir}"'
            subprocess.run(["pkexec", "bash", "-c", command], check=True, capture_output=True, text=True)
            self.log.emit("✅ Successfully Unmounted and Deleted.")
            self.done.emit(True)

        except subprocess.CalledProcessError as e:
            # This block will catch specific subprocess errors
            self.log.emit(f"❌ Deletion failed: {e.returncode}.")
            self.log.emit(f"❌ Error output: {e.stderr}")
            self.done.emit(False)

            # If unmounting and deleting failed, try deleting normally
            self.log.emit("Only Deleting Normally.")
            command = f'rm -rf "{overlay_dir}"'
            subprocess.run(["pkexec", "bash", "-c", command], check=True, capture_output=True, text=True)
            self.log.emit("✅ Successfully Deleted.")
            self.done.emit(True)

        except Exception as e:    self.log.emit(f"❌ General error occurred: {str(e)}") ; self.done.emit(False)



class RunAnalyze(QThread):

    log = pyqtSignal(str) ; started_signal = pyqtSignal(str)

    def __init__(self, exe_file, tprefix=None, preso=None):
        super().__init__()
        self.tprefix = tprefix
        self.preso = preso ; self.wine = 'wine'; self.exe_file = exe_file

    def run(self):
