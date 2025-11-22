import os, time, subprocess
from PyQt5.QtCore import QThread, pyqtSignal


class Prefix(QThread):
    log = pyqtSignal(str); done = pyqtSignal(bool)

    def __init__(self, num, exe_path=None, bprefix_path=None, deletion=None):
        super().__init__()
        self.wine = 'wine'
        self.num = num
        self.bprefix_path = bprefix_path
        self.exe_path = exe_path

    def run(self):
        if self.num == 3:    self.setup_temp_prefix()
        elif self.num == 4:    self.delet_temp_prefix()



    def setup_temp_prefix(self):

        overlay_dir = self.setup_native_overlay()

        if not overlay_dir:    self.done.emit(False); return
        if not self.initialize_wine_prefix(overlay_dir):    self.done.emit(False); return
        self.done.emit(True)

    def setup_native_overlay(self):
        try:
            overlay_dir = os.path.join(self.exe_path, ".wine_temp_noverlay")
            os.makedirs(overlay_dir, exist_ok=True)
            for subdir in ("upper", "work", "merged"):    os.makedirs(os.path.join(overlay_dir, subdir), exist_ok=True)

            lower_dir = self.bprefix_path
            upper_dir, work_dir, merged_dir = (os.path.join(overlay_dir, d) for d in ("upper", "work", "merged"))

            self.log.emit(f"Overlay setup paths: lower={lower_dir}, upper={upper_dir}, work={work_dir}, merged={merged_dir}")

            # Overlay mount command
            command = [
                'pkexec', 'mount', '-t', 'overlay', 'overlay', '-o',
                f'lowerdir={lower_dir},upperdir={upper_dir},workdir={work_dir}', merged_dir
            ]
            self.log.emit(f"Running mount command: {' '.join(command)}")

            subprocess.run(command, check=True)
            self.log.emit("Overlay mounted successfully.")

            # Check if the merged directory exists
            if not os.path.exists(merged_dir) or not os.path.isdir(merged_dir):
                self.log.emit("❌ Overlay setup failed.")
                return None

            return overlay_dir

        except subprocess.CalledProcessError as e:    self.log.emit(f"❌ Overlay setup failed: {e}"); self.log.emit(f"stderr: {e.stderr}")
        except Exception as e:    self.log.emit(f"❌ Overlay setup failed: {e}")
        return None

    def initialize_wine_prefix(self, overlay_dir):
        try:
            drive_c_dir = os.path.join(overlay_dir, "merged", "drive_c", "windows")
            os.makedirs(drive_c_dir, exist_ok=True)

            merged_dir = os.path.join(overlay_dir, "merged")
            env = {**os.environ, "WINEPREFIX": merged_dir, "WINEDEBUG": "-all", "WINEARCH": "win64"}

            subprocess.run([self.wine, "wineboot", "-u"], env=env, cwd=os.path.dirname(self.exe_path), check=True, capture_output=True)
            subprocess.run([self.wine, "wine", "reg", "add", "HKCU\\Software\\Wine\\Wine\\Config", "/v", "Version", "/d", "10.0", "/f"], env=env)

            self.log.emit("✅ Wine prefix initialized with Win10 successfully.")
            return True
        except subprocess.CalledProcessError as e:    self.log.emit(f"❌ Wine prefix initialization failed: {e}")
        except Exception as e:    self.log.emit(f"❌ Wine prefix initialization failed: {e}")
        return False


    def delet_temp_prefix(self):
        overlay_dir = os.path.join(self.exe_path, ".wine_temp_noverlay")
        merged_dir = os.path.join(overlay_dir, "merged")

        if not os.path.exists(overlay_dir):    self.log.emit("ℹ️ No Temp Prefix found."); return

        try:
            # Check if the overlay is mounted
            result = subprocess.run(["mount"], check=True, capture_output=True, text=True)
            if merged_dir in result.stdout:    self.log.emit(f"ℹ️ {merged_dir} is mounted.")
            else:    self.log.emit(f"ℹ️ {merged_dir} is not mounted."); return

            # Unmount the overlay if it's mounted
            self.log.emit(f"Attempting to Unmount{merged_dir} and Delete {overlay_dir} ...")
            command = f'umount "{merged_dir}" && rm -rf "{overlay_dir}"'

            # Chain both commands: umount and rm -rf, using pkexec with bash -c
            result = subprocess.run ( ["pkexec", "bash", "-c", command], check=True, capture_output=True, text=True )

            self.log.emit( f"stdout: {result.stdout}" ); self.log.emit( f"stderr: {result.stderr}" )
            self.log.emit( f"✅ Successfully unmounted {merged_dir} and deleted {overlay_dir}.")

        except subprocess.CalledProcessError as e:    self.log.emit(f"❌ Operation failed: {e}")
        except Exception as e:    self.log.emit(f"❌ Unexpected error: {e}")




class Launch(QThread):
    log = pyqtSignal(str); started_signal = pyqtSignal(str)

    def __init__(self, tprefix, stable_env, wine, exe_file, pref_res=None, nstable_env=None, mono_mod_env=None):
        super().__init__()
        self.tprefix = tprefix
        self.stable_env = stable_env
        self.wine = wine
        self.exe = exe_file
        self.pref_res = pref_res
        self.nstable_env = nstable_env
        self.mono_mod_env = mono_mod_env

    def run(self):
        cmd = self.build_command()
        self.started_signal.emit(f"🚀 Launching Command:\n$ {cmd}")
        proc = self.launch(cmd)

        if proc and proc.returncode == 0:
            self.log.emit("✅ Execution finished.")
        else:
            self.log.emit("⚠️ EXE exited with error.")

    def build_command(self):
        cmd = f"{self.tprefix} {self.pref_res} {self.stable_env} " \
              f"{self.nstable_env if self.nstable_env else ''} " \
              f"{self.wine} " \
              f"{self.mono_mod_env if self.mono_mod_env else ''} " \
              f"{self.exe}"
        return cmd

    def launch(self, cmd):
        try:
            terminal_cmd = f"x-terminal-emulator -e 'bash -c \"{cmd}; echo Done; exec bash\"'"

            proc = subprocess.Popen(
                terminal_cmd,
                cwd=os.path.dirname(self.exe),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                shell=True,
                bufsize=1
            )

            stdout, stderr = proc.communicate(timeout=90)
            self.log.emit(stdout)
            if stderr:
                self.log.emit(f"⚠️ Error Output: {stderr}")
            return proc

        except subprocess.TimeoutExpired:
            self.log.emit("⏱️ Process timed out, killing.")
            proc.kill()
            return None
        except Exception as e:
            self.log.emit(f"❌ Launch failed: {e}")
            return None
