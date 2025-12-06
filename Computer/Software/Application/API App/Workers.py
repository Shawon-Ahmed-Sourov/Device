import os, time, queue, threading, subprocess
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

    log = pyqtSignal(str) ; done = pyqtSignal(bool)

    def __init__(self, exe_path, exe_file, tprefix_path =None, BepInEx_dll=None, preso=None):
        super().__init__()

        self.wine = "wine" ; self.exe_file = exe_file ; self.tprefix_path = tprefix_path # Fin  Merged-Dir of N.OverlayFS
        self.exe_path =exe_path ; self.BepInEx_dll =BepInEx_dll ; self.preso = preso

        self.proc = None

    def run(self):

        cmd, merged_env = self._build_command()
        self._launch_exe(cmd, merged_env)


    def _build_command(self):

        env1 = {**os.environ, "WINEPREFIX": self.tprefix_path}
        env2 = {
            "WINE_FULLSCREEN": "0",
            "WINEDEBUG": "+timestamp,+warn",
            "WINE_ALLOW_LARGE_ALLOCS": "1",
            "WINEESYNC": "1", "WINEFSYNC": "1", "WINEASYNC": "0"
        }
        merged_env = {**env1, **env2}
        
        cmd = [self.wine]
        if self.BepInEx_dll:    cmd += ["mono", self.BepInEx_dll]
        cmd += [self.exe_file]

        return cmd, merged_env

    def _launch_exe(self, cmd, env):

        self.log.emit(f"🚀 Launching EXE:\n$ {' '.join(cmd)}")

        try:
            self.proc = subprocess.Popen(cmd, env=env, cwd=os.path.dirname(self.exe_file),
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)

            if not self.proc : raise Exception("Failed to start the process.")

            self._monitor_proc(self.proc)

        except Exception as e:    self.log.emit(f"❌ Error launching game: {e}") ; self.done.emit(False)


    def _monitor_proc(self, proc):
        try:
            if proc is None:    self.log.emit("❌ Process is None.") ; self.done.emit(False) ; return

            # Continuous non-blocking read from stdout and stderr
            while True:
                output = proc.stdout.readline()
                if output:    self.log.emit(output.strip())

                error = proc.stderr.readline()
                if error:    self.log.emit(f"ERROR: {error.strip()}")

                return_code = proc.poll()
                if return_code is not None:
                    if return_code != 0:
                        self.log.emit(f"❌ Process failed with return code {return_code}")
                        break

                time.sleep(0.1)
        except Exception as e:    self.log.emit(f"❌ Error while monitoring process: {e}") ; self.done.emit(False)
        else:    self.done.emit(True)  # Signal completion when the process ends



