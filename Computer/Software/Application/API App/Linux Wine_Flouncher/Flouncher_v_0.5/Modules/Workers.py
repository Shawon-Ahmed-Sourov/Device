# Date : 5 Dec 2025
# Workers.py
import os, pty, time, queue, shutil, threading, subprocess
from PyQt5.QtCore import QThread, pyqtSignal


# -------------------------
# Common Utility Functions
# -------------------------
def run_command(cmd, capture_output=False, check=True, env=None, cwd=None, text=True):
    try:
        return subprocess.run(cmd, check=check, capture_output=capture_output, env=env, cwd=cwd, text=text)
    except subprocess.CalledProcessError as e:    return e


def ensure_dirs_exist(dirs):
    """Ensure all directories in the given list exist."""
    try:
        [os.makedirs(d, exist_ok=True) for d in dirs]
        return True
    except OSError as e:    return f"❌ Directory creation failed: {e}"

def is_mounted(merged):
    """Check if a directory is mounted."""
    try:
        return merged in run_command(["mount"], capture_output=True, text=True).stdout
    except Exception:    return False

def remove_path(path):
    """Safely remove a path with elevated privileges."""
    try:
        run_command(["pkexec", "rm", "-rf", path])
        return True
    except Exception as e:    return f"❌ Remove failed: {e}"


# -------------------------
# Prefix Manager (Refactored)
# -------------------------
class Prefix(QThread):
    
    log = pyqtSignal(str) ; done = pyqtSignal(bool)

    def __init__(self, num: int, exe_path, bprefix_path=None):
        super().__init__()
        self.num = num
        self.exe_path = exe_path ; self.bprefix_path = bprefix_path
        self.wine = "wine"

    def run(self):
        try:
            if   self.num == 3:    self.done.emit(self._create_temp_prefix())
            elif self.num == 4:    self.done.emit(self._delete_temp_prefix())
            else:    self.log.emit("❌ Invalid operation number.") ; self.done.emit(False)
        except Exception as e:     self.log.emit(f"❌ Prefix thread error: {e}") ; self.done.emit(False)


    def _delete_temp_prefix(self):
        """Delete the temporary Wine prefix."""
        overlay_dir = os.path.join(self.exe_path, ".wine_temp_noverlay")
        merged = os.path.join(overlay_dir, "merged")

        if not os.path.exists(overlay_dir):    self.log.emit("ℹ️ No prefix found") ; return True
        if not is_mounted(merged):    return remove_path(overlay_dir)
        return self._unmount_remove(merged, overlay_dir)

    def _unmount_remove(self, merged, overlay_dir):
        """Unmount and remove overlay directory with a single password prompt."""
        try:
            # Quote paths properly to handle spaces
            merged_quoted = f'"{merged}"'
            overlay_dir_quoted = f'"{overlay_dir}"'

            # Combine unmount and removal commands into one single bash command
            unmount_and_remove_cmd=f"""
            fusermount -u {merged_quoted} || pkexec umount -l {merged_quoted} || pkexec umount {merged_quoted}
            [ ! -d {overlay_dir_quoted} ] && echo "Directory already removed." || pkexec rm -rf {overlay_dir_quoted}
            """

            # Log the action
            self.log.emit("Attempting to unmount and delete overlay directory...")

            # Run the combined command with pkexec
            run_command(["pkexec", "bash", "-c", unmount_and_remove_cmd], capture_output=True, text=True)

            # Check if the overlay directory is removed
            if not os.path.exists(overlay_dir):    self.log.emit("✅ Overlay Directory removed.") ; return True
            else:    self.log.emit(f"❌ Failed to remove Directory: {overlay_dir}") ; return False

        except Exception as e:    self.log.emit(f"⚠️ Error while Unmounting or Deletion: {e}") ; return False


    def _create_temp_prefix(self):
        """Create a temporary Wine prefix."""
        if not self.exe_path or not self.bprefix_path:    self.log.emit("❌ No Path of exe or BPrefix.") ; return False

        overlay_dir = os.path.join(self.exe_path, ".wine_temp_noverlay")
        dirs = {p: os.path.join(overlay_dir, p) for p in ("upper", "work", "merged")}

        if not ensure_dirs_exist(dirs.values()):    self.log.emit(f"❌ Couldn't prepare overlay dirs.") ; return False

        fs_type = self._detect_fs(self.exe_path)

        if not self._mount_overlay(fs_type, dirs["merged"], overlay_dir):    return False
        return self._init_wine_temp_prefix(dirs["merged"])

    def _detect_fs(self, exe_path):
        """Detect filesystem type with error handling."""
        try:
            out = run_command(["df", "-T", exe_path], capture_output=True, text=True, check=True).stdout
            fs_type = out.splitlines()[1].split()[1].lower()
            self.log.emit(f"Detected Filesystem: {fs_type}")
            return fs_type
        except subprocess.CalledProcessError as e: self.log.emit(f"❌ Unable to detect filesystem: {e}") ; return "unknown"

    def _mount_overlay(self, fs_type, merged, overlay_dir):
        """Mount the overlay filesystem ensuring the base prefix is remain pure & read-only."""
        lower = self.bprefix_path  # base Wine prefix (read-only)
        mount_cmd = []

        if fs_type in ["ext4", "xfs"]:  # Using pkexec to mount with overlay
            mount_cmd = ["pkexec", "mount", "-t", "overlay", "overlay",   "-o", f"lowerdir={lower},upperdir={overlay_dir}/upper,workdir={overlay_dir}/work", merged]
        elif fs_type == "fuseblk":  # Using fuse-overlayfs for fuse filesystems
            mount_cmd = ["fuse-overlayfs", "-o", f"lowerdir={lower},upperdir={overlay_dir}/upper,workdir={overlay_dir}/work", merged]
        else:    self.log.emit(f"❌ Unsupported filesystem type: {fs_type}") ; return False

        try:    run_command(mount_cmd) ; return True
        except Exception as e:    self.log.emit(f"❌ Mount failed: {e}") ; return False

    def _init_wine_temp_prefix(self, merged):
        """Prepare the merged directories and initialize the Wine prefix."""
        try:
            # Step 1: Prepare the directories
            os.makedirs(os.path.join(merged, "drive_c", "windows"), exist_ok=True)

            # Step 2: Set up the Wine environment
            env = {**os.environ, "WINEPREFIX": merged, "WINEDEBUG": "-all", "WINEUPDATE": "0", "WINEDLLOVERRIDES": "dll=ignore", "WINEPOLICY": "1"}
        
            # Step 3: Initialize the Wine prefix
            self.log.emit("⚡ Initializing Wine Prefix...")
            run_command([self.wine, "wineboot"], env=env, cwd=os.path.dirname(self.exe_path), check=True)

            # Step 4: Check for the Wine version in the registry
            reg_check = run_command([self.wine, "reg", "query", "HKCU\\Software\\Wine\\Wine\\Config", "/v", "Version"], env=env, capture_output=True)
            if "Version" not in getattr(reg_check, "stdout", ""):
                run_command([self.wine, "reg", "add", "HKCU\\Software\\Wine\\Wine\\Config", "/v", "Version", "/d", "10.0", "/f"], env=env)

            self.log.emit("✅ Wine prefix ready (Win10).")
            return True
        
        except OSError as e:    self.log.emit(f"❌ Un-Preparable merged dirs: {e}")
        except Exception as e:    self.log.emit(f"❌ Wine init Failed: {e}")
        return False

# -------------------------
# Run Analyze Worker (Refactored)
# -------------------------

class RunAnalyze(QThread):
    log = pyqtSignal(str) ; done = pyqtSignal(bool)

    def __init__(self, exe_path, exe_file, tprefix_path=None, BepInEx_dll=None ):
        super().__init__()
        self.tprefix_path = tprefix_path ; self.wine = "wine" ; self.exe_file = exe_file
        self.BepInExEx_dll = BepInEx_dll

    def run(self):
        try:
            cmd, env = self._build_command()
            self._launch_exe(cmd, env)
        except Exception as e:    self.log.emit(f"❌ Run error: {e}") ; self.done.emit(False)

    def _build_command(self):
        """Build the command to run the EXE."""
        env = {**os.environ, "WINEPREFIX": self.tprefix_path or "", "WINE_FULLSCREEN": "0", "WINEDEBUG": "+timestamp,+warn", "WINE_ALLOW_LARGE_ALLOCS": "1", "WINEESYNC": "1", "WINEFSYNC": "1", "WINEASYNC": "0"}

        # Method name : Progmatically List-Based  shell-command-construction.
        cmd = [self.wine]
        if self.BepInExEx_dll:    cmd += ["mono", self.BepInExEx_dll]
        cmd += [self.exe_file]
        return cmd, env

    def _launch_exe(self, cmd, env):    # Launch by PTY to avoid EBADF error.( import os,pty )
        self.log.emit(f"Launching EXE: {' '.join(cmd)}")
        try:
            master_fd, slave_fd = pty.openpty()  # Create Pseudo-Terminal
            proc = subprocess.Popen(
                cmd, env=env, cwd=os.path.dirname(self.exe_file),
                stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
                text=True, bufsize=1, close_fds=True
            )
            os.close(slave_fd)
            self._monitor_pty(proc, master_fd)
        except Exception as e:    self.log.emit(f"❌ Launch failed: {e}"); self.done.emit(False)

    def _monitor_pty(self, proc, master_fd):    # Monitor the PTY and process output.
        missing = set()  # For missing DLLs
        try:
            while True:
                try:
                    data = os.read(master_fd, 1024).decode(errors="ignore")
                    if data:
                        for line in data.splitlines():
                            self.log.emit(line)
                                                # Check for missing DLLs in output
                            if ".dll" in line.lower() and any(x in line.lower() for x in ("not found", "cannot", "error")):    missing.add(line.split()[0].lower())
                        if proc.poll() is not None:    break
                except OSError:    break

        finally:
            os.close(master_fd)
            if missing:     # Handle missing DLLs
                with open(os.path.join( os.path.dirname( self.exe_file ), "Analyzable-logs.txt"), "w") as f:
                    f.write( "\n".join(sorted ( missing ) ) )
                self.log.emit( f"❗ Missing DLLs: {', '.join( sorted( missing ) ) }" )
            else:    self.log.emit( "✅ No missing DLLs detected." )
        
            self.done.emit(proc.returncode == 0)

# -------------------------
# Winetricks Launcher
# -------------------------
class InstallDllsWorker(QThread):
    log = pyqtSignal(str)

    def __init__(self, base, wine_cmd="wine"):
        super().__init__()
        self.base = base ; self.wine = wine_cmd

    def run(self):
        if shutil.which("winetricks") is None:    self.log.emit("❌ winetricks isn't installed.") ; return

        try:
            self.log.emit("⚡ Launching Winetricks...")
            subprocess.Popen(["winetricks"], env={**os.environ, "WINEPREFIX": self.base})
            self.log.emit(f"✅ Tip: $ WINEPREFIX={self.base} winetricks")
        except Exception as e:    self.log.emit(f"❌ Failed to start winetricks: {e}")

