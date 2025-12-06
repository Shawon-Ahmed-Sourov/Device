# workers_refactored.py
import os, time, queue, threading, subprocess, shutil
from PyQt5.QtCore import QThread, pyqtSignal

# -------------------------
# Utility: simple logger helper
# -------------------------
def _run(cmd, check=True, capture_output=False, env=None, cwd=None, text=True):
    return subprocess.run(cmd, check=check, capture_output=capture_output, env=env, cwd=cwd, text=text)

# -------------------------
# Minimal job class (kept)
# -------------------------
class CJob:
    def __init__(self, num, path, obj_name):
        self.num = num
        self.path = path
        self.obj_name = obj_name

    def analyze(self):
        full_path = os.path.join(self.path, self.obj_name)
        return os.path.isdir(full_path) if self.num == 0 else os.path.isfile(full_path) if self.num == 1 else None

# -------------------------
# Prefix manager (create / init / delete) - safe + compact
# -------------------------
class Prefix(QThread):
    log = pyqtSignal(str)
    done = pyqtSignal(bool)

    def __init__(self, num, exe_path=None, bprefix_path=None, wine_cmd="wine"):
        super().__init__()
        self.num = num            # 3 => create, 4 => delete
        self.exe_path = exe_path
        self.bprefix_path = bprefix_path
        self.wine = wine_cmd

    def run(self):
        try:
            if self.num == 3:
                ok = self._create_temp_prefix()
                self.done.emit(bool(ok))
            elif self.num == 4:
                ok = self._delete_temp_prefix()
                # deletion logs internally; if nothing found it's ok
                self.done.emit(bool(ok))
            else:
                self.log.emit("❌ No Prefix Action Taken.")
                self.done.emit(False)
        except Exception as e:
            self.log.emit(f"❌ Unexpected error: {e}")
            self.done.emit(False)

    # ---- create + initialize ----
    def _create_temp_prefix(self):
        overlay_dir = self._create_overlay_dirs()
        if not overlay_dir: return False

        if not self._mount_overlay(overlay_dir): return False

        merged = os.path.join(overlay_dir, "merged")
        if not self._ensure_drive_dirs(merged): 
            self.log.emit("❌ Failed preparing merged drive dirs.")
            return False

        return self._initialize_wine_prefix(merged)

    def _create_overlay_dirs(self):
        if not self.exe_path or not self.bprefix_path:
            self.log.emit("❌ exe_path or bprefix_path missing.")
            return None
        overlay_dir = os.path.join(self.exe_path, ".wine_temp_noverlay")
        try:
            os.makedirs(overlay_dir, exist_ok=True)
            for p in ("upper", "work", "merged"):
                os.makedirs(os.path.join(overlay_dir, p), exist_ok=True)
            return overlay_dir
        except OSError as e:
            self.log.emit(f"❌ Could not create overlay dirs: {e}")
            return None

    def _mount_overlay(self, overlay_dir):
        lower = self.bprefix_path
        merged = os.path.join(overlay_dir, "merged")
        # Try native overlay first; fallback to fuse-overlayfs
        native_cmd = ["pkexec", "mount", "-t", "overlay", "overlay", "-o",
                      f"lowerdir={lower},upperdir={overlay_dir}/upper,workdir={overlay_dir}/work", merged]
        fuse_cmd   = ["fuse-overlayfs", "-o", f"lowerdir={lower},upperdir={overlay_dir}/upper,workdir={overlay_dir}/work", merged]

        # attempt native mount, then fallback
        for cmd, label in ((native_cmd, "native OverlayFS"), (fuse_cmd, "fuse-overlayfs")):
            try:
                self.log.emit(f"Mounting ({label}): {' '.join(cmd)}")
                subprocess.run(cmd, check=True, capture_output=True, text=True)
                self.log.emit("✅ Overlay Mounted.")
                return True
            except subprocess.CalledProcessError as e:
                self.log.emit(f"⚠️ Mount failed ({label}): {e}")
                continue
        self.log.emit("❌ All overlay mount attempts failed.")
        return False

    def _ensure_drive_dirs(self, merged):
        try:
            os.makedirs(os.path.join(merged, "drive_c", "windows"), exist_ok=True)
            return True
        except OSError as e:
            self.log.emit(f"❌ Error creating drive_c directories: {e}")
            return False

    def _initialize_wine_prefix(self, merged_dir):
        env = {**os.environ, "WINEPREFIX": merged_dir, "WINEUPDATE": "0", "WINEDEBUG": "-all", "WINEARCH": "win64", "WINEDLLOVERRIDES": "dll=ignore"}
        try:
            # run wineboot once to ensure prefix created; safe-guard with winecfg fallback only if needed
            self.log.emit("⚡ Initializing Wine prefix (wineboot)...")
            subprocess.run([self.wine, "wineboot", "-u"], env=env, cwd=os.path.dirname(self.exe_path), check=True, capture_output=True, text=True)
            # Ensure Windows version key exists
            reg_check = subprocess.run([self.wine, "reg", "query", "HKCU\\Software\\Wine\\Wine\\Config", "/v", "Version"],
                                      env=env, cwd=os.path.dirname(self.exe_path), capture_output=True, text=True)
            if "Version" not in reg_check.stdout:
                subprocess.run([self.wine, "reg", "add", "HKCU\\Software\\Wine\\Wine\\Config", "/v", "Version", "/d", "10.0", "/f"],
                                env=env, cwd=os.path.dirname(self.exe_path), check=True, capture_output=True, text=True)
            self.log.emit("✅ Windows set to Win10 in Wine prefix.")
            return True
        except subprocess.CalledProcessError as e:
            self.log.emit(f"❌ Couldn't initialize Wine prefix: {getattr(e, 'stderr', str(e))}")
            return False

    # ---- delete + cleanup (robust) ----
    def _delete_temp_prefix(self):
        overlay_dir = os.path.join(self.exe_path, ".wine_temp_noverlay")
        merged = os.path.join(overlay_dir, "merged")
        if not os.path.exists(overlay_dir):
            self.log.emit("ℹ️ No Temp Prefix found.")
            return True

        # If merged isn't mounted, try safe deletion
        if not self._is_mount_active(merged):
            self.log.emit("ℹ️ Overlay not mounted; deleting files.")
            return self._safe_remove(overlay_dir)

        # Try unmount + delete with several fallbacks
        return self._unmount_and_remove_with_fallbacks(merged, overlay_dir)

    def _is_mount_active(self, merged):
        try:
            out = subprocess.run(["mount"], capture_output=True, text=True, check=True).stdout
            return merged in out
        except subprocess.CalledProcessError:
            return False

    def _unmount_and_remove_with_fallbacks(self, merged, overlay_dir):
        # attempt sequence: fusermount -u, pkexec umount -l, pkexec umount, lazy unmount, then rm
        attempts = [
            (["fusermount", "-u", merged], "fusermount -u"),
            (["pkexec", "umount", "-l", merged], "pkexec umount -l"),
            (["pkexec", "umount", merged], "pkexec umount"),
            (["umount", "-l", merged], "umount -l"),
        ]
        for cmd, label in attempts:
            try:
                self.log.emit(f"Attempting unmount ({label})")
                subprocess.run(cmd, check=True, capture_output=True, text=True)
                time.sleep(0.1)
                if not self._is_mount_active(merged):
                    self.log.emit(f"✅ Unmounted with {label}")
                    return self._safe_remove(overlay_dir)
            except subprocess.CalledProcessError as e:
                self.log.emit(f"⚠️ Unmount {label} failed: {getattr(e, 'stderr', str(e))}")
                continue

        # final resort: pkexec rm -rf
        try:
            self.log.emit("Attempting forced deletion via pkexec rm -rf")
            subprocess.run(["pkexec", "rm", "-rf", overlay_dir], check=True, capture_output=True, text=True)
            self.log.emit("✅ Successfully Unmounted and Deleted.")
            return True
        except subprocess.CalledProcessError as e:
            self.log.emit(f"❌ Forced deletion failed: {getattr(e, 'stderr', str(e))}")
            # Last try: local rm (may fail if permission)
            return self._safe_remove(overlay_dir)

    def _safe_remove(self, path):
        try:
            if os.path.exists(path):
                shutil.rmtree(path)
            self.log.emit("✅ Deleted temp prefix.")
            return True
        except Exception as e:
            self.log.emit(f"❌ Deletion failed: {e}")
            return False

# -------------------------
# RunAnalyze: non-blocking launch + real-time logs
# -------------------------
class RunAnalyze(QThread):
    log = pyqtSignal(str)
    done = pyqtSignal(bool)

    def __init__(self, exe_path, exe_file, tprefix_path=None, BepInEx_dll=None, preso=None, wine_cmd="wine"):
        super().__init__()
        self.wine = wine_cmd
        self.exe_file = exe_file
        self.tprefix_path = tprefix_path
        self.exe_path = exe_path
        self.BepInEx_dll = BepInEx_dll
        self.preso = preso
        self.proc = None

    def run(self):
        try:
            cmd, merged_env = self._build_command()
            self._launch_exe(cmd, merged_env)
        except Exception as e:
            self.log.emit(f"❌ Run error: {e}")
            self.done.emit(False)

    def _build_command(self):
        env1 = {**os.environ, "WINEPREFIX": self.tprefix_path or ""}
        env2 = {
            "WINE_FULLSCREEN": "0",
            "WINEDEBUG": "+timestamp,+warn",
            "WINE_ALLOW_LARGE_ALLOCS": "1",
            "WINEESYNC": "1", "WINEFSYNC": "1", "WINEASYNC": "0"
        }
        merged_env = {**env1, **env2}
        cmd = [self.wine]
        if self.BepInEx_dll:
            cmd += ["mono", self.BepInEx_dll]
        cmd += [self.exe_file]
        return cmd, merged_env

    def _launch_exe(self, cmd, env):
        self.log.emit(f"🚀 Launching EXE:\n$ {' '.join(cmd)}")
        try:
            # Merge stderr into stdout and open pipes
            self.proc = subprocess.Popen(cmd, env=env, cwd=os.path.dirname(self.exe_file),
                                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                         text=True, bufsize=1)
            if not self.proc:
                raise RuntimeError("Failed to start process")
            self._monitor_proc(self.proc)
        except Exception as e:
            self.log.emit(f"❌ Error launching game: {e}")
            self.done.emit(False)

    def _monitor_proc(self, proc):
        q = queue.Queue()

        def reader_thread():
            try:
                for line in iter(proc.stdout.readline, ''):
                    q.put(line.rstrip())
            except Exception as e:
                q.put(f"❌ Reader error: {e}")
            finally:
                try: proc.stdout.close()
                except Exception: pass

        threading.Thread(target=reader_thread, daemon=True).start()

        missing_dlls = set()
        # Consume queue until process ends and queue empty
        while proc.poll() is None or not q.empty():
            try:
                line = q.get(timeout=0.15)
                if line:
                    self.log.emit(line)
                    low = line.lower()
                    if ".dll" in low and ("not found" in low or "cannot" in low or "error" in low):
                        # pick probable dll token
                        token = line.split()[0].lower()
                        missing_dlls.add(token)
            except queue.Empty:
                pass

        proc.wait()
        # write missing dlls log (if any)
        try:
            if missing_dlls:
                with open(os.path.join(os.path.dirname(self.exe_file), "Analyzable-logs.txt"), "w") as f:
                    f.write("\n".join(sorted(missing_dlls)))
                self.log.emit(f"❗ Missing DLLs: {', '.join(sorted(missing_dlls))}")
            else:
                self.log.emit("✅ No missing DLLs detected.")
        except Exception as e:
            self.log.emit(f"⚠️ Couldn't write missing-dlls file: {e}")

        if proc.returncode == 0:
            self.log.emit("✅ Process finished successfully.")
            self.done.emit(True)
        else:
            self.log.emit(f"⚠️ EXE exited with code {proc.returncode}")
            self.done.emit(False)

# -------------------------
# Small helper worker to start winetricks (kept simple)
# -------------------------
class InstallDllsWorker(QThread):
    log = pyqtSignal(str)
    def __init__(self, base, wine_cmd="wine"):
        super().__init__(); self.base = base; self.wine = wine_cmd
    def run(self):
        if shutil.which("winetricks") is None:
            self.log.emit("❌ winetricks isn't installed."); return
        try:
            self.log.emit("⚡ Opening Winetricks GUI...")
            subprocess.Popen(["winetricks"], env={**os.environ, "WINEPREFIX": self.base})
            self.log.emit(f"✅ Terminal-Command: $ WINEPREFIX={self.base} winetricks")
        except Exception as e:
            self.log.emit(f"❌ Failed to start winetricks: {e}")