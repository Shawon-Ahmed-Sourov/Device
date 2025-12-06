# Workers_unified.py
import os
import time
import queue
import shutil
import threading
import subprocess
from typing import Optional
from PyQt5.QtCore import QThread, pyqtSignal

# -----------------------
# Utilities
# -----------------------
def run(cmd, check=True, env=None, cwd=None, capture_output=False, text=True):
    return subprocess.run(cmd, check=check, env=env, cwd=cwd,
                          capture_output=capture_output, text=text)

def sh_call(cmd, check=False):
    try:
        return subprocess.run(cmd, check=check)
    except subprocess.CalledProcessError as e:
        return e

# -----------------------
# Prefix manager (create / init / delete)
# -----------------------
class Prefix(QThread):
    log = pyqtSignal(str)
    done = pyqtSignal(bool)

    def __init__(self, action:int, exe_path:Optional[str]=None, base_prefix:Optional[str]=None, wine_cmd:str="wine"):
        """
        action: 3 => create temp prefix, 4 => delete temp prefix
        exe_path: folder where .wine_temp_noverlay will be created
        base_prefix: the lowerdir (real prefix to overlay)
        wine_cmd: 'wine' or full path
        """
        super().__init__()
        self.action = action
        self.exe_path = exe_path
        self.base_prefix = base_prefix
        self.wine = wine_cmd

    # --- run dispatcher ---
    def run(self):
        try:
            if self.action == 3:
                ok = self._create_temp_prefix()
                self.done.emit(bool(ok))
            elif self.action == 4:
                ok = self._delete_temp_prefix()
                # _delete_temp_prefix emits logs itself
                self.done.emit(bool(ok))
            else:
                self.log.emit("❌ No Prefix Action Taken.")
                self.done.emit(False)
        except Exception as e:
            self.log.emit(f"❌ Prefix thread error: {e}")
            self.done.emit(False)

    # --- create ---
    def _create_temp_prefix(self) -> bool:
        if not self.exe_path or not self.base_prefix:
            self.log.emit("❌ Missing exe_path or base_prefix.")
            return False

        overlay_dir = os.path.join(self.exe_path, ".wine_temp_noverlay")
        upper = os.path.join(overlay_dir, "upper")
        work = os.path.join(overlay_dir, "work")
        merged = os.path.join(overlay_dir, "merged")
        try:
            for d in (upper, work, merged):
                os.makedirs(d, exist_ok=True)
        except OSError as e:
            self.log.emit(f"❌ Failed to prepare overlay dirs: {e}")
            return False

        fs = self._detect_fs(self.exe_path)
        self.log.emit(f"⚙️ Filesystem detected: {fs}")

        # try native overlay (requires pkexec/mount) then fuse-overlayfs
        if fs in ("ext4", "btrfs", "xfs"):
            cmd = ["pkexec", "mount", "-t", "overlay", "overlay",
                   "-o", f"lowerdir={self.base_prefix},upperdir={upper},workdir={work}", merged]
            used = "native overlay"
        else:
            cmd = ["fuse-overlayfs", "-o", f"lowerdir={self.base_prefix},upperdir={upper},workdir={work}", merged]
            used = "fuse-overlayfs"

        self.log.emit(f"⚡ Attempting to mount overlay ({used})")
        try:
            run(cmd, check=True)
        except Exception as e:
            self.log.emit(f"❌ Overlay mount failed ({used}): {e}")
            return False

        # initialize wineprefix minimally
        env = {**os.environ, "WINEPREFIX": merged, "WINEDLLOVERRIDES": "dll=ignore", "WINEDEBUG": "-all", "WINEARCH":"win64", "WINEUPDATE":"0"}
        try:
            os.makedirs(os.path.join(merged, "drive_c", "windows"), exist_ok=True)
            # only run wineboot if no registry file exists
            if not os.path.exists(os.path.join(merged, "user.reg")):
                self.log.emit("⚡ Running wineboot to initialize prefix...")
                run([self.wine, "wineboot", "-u"], env=env, cwd=os.path.dirname(self.exe_path))
            # ensure Win10 setting (safe/write registry)
            try:
                out = run([self.wine, "reg", "query", r"HKCU\Software\Wine\Wine\Config", "/v", "Version"],
                          env=env, cwd=os.path.dirname(self.exe_path), capture_output=True)
                if "Version" not in out.stdout:
                    run([self.wine, "reg", "add", r"HKCU\Software\Wine\Wine\Config", "/v", "Version", "/d", "10.0", "/f"],
                        env=env, cwd=os.path.dirname(self.exe_path))
            except Exception:
                # non-fatal: continue
                pass

            self.log.emit("✅ Temp prefix created and initialized.")
            return True
        except Exception as e:
            self.log.emit(f"❌ Failed to initialize wine prefix: {e}")
            # try cleanup on failure
            self._safe_unmount_and_delete(merged, overlay_dir)
            return False

    def _detect_fs(self, path):
        try:
            out = run(["df", "-T", path], capture_output=True).stdout
            return out.splitlines()[1].split()[1].lower()
        except Exception:
            return "unknown"

    # --- delete ---
    def _delete_temp_prefix(self) -> bool:
        if not self.exe_path:
            self.log.emit("❌ Missing exe_path for deletion.")
            return False

        overlay_dir = os.path.join(self.exe_path, ".wine_temp_noverlay")
        merged = os.path.join(overlay_dir, "merged")
        if not os.path.exists(overlay_dir):
            self.log.emit("ℹ️ No Temp Prefix found.")
            return True

        # If not mounted, just delete
        if not self._is_mounted(merged):
            self.log.emit("ℹ️ Overlay not mounted; removing directory.")
            return self._safe_delete_dir(overlay_dir)

        self.log.emit("⚠️ Overlay is mounted; attempting unmount & delete...")
        return self._safe_unmount_and_delete(merged, overlay_dir)

    def _is_mounted(self, merged):
        try:
            m = run(["mount"], capture_output=True).stdout
            return merged in m
        except Exception:
            return False

    def _safe_unmount_and_delete(self, merged, overlay_dir) -> bool:
        # try multiple unmount strategies
        attempts = [
            (["fusermount", "-u", merged], False),
            (["pkexec", "umount", "-l", merged], False),  # lazy unmount
            (["pkexec", "umount", merged], False),
            (["pkexec", "bash", "-c", f'umount "{merged}" || true'], False)
        ]
        last_exc = None
        for cmd, _ in attempts:
            try:
                self.log.emit(f"⚡ Running: {' '.join(cmd)}")
                run(cmd, check=True)
                time.sleep(0.1)
                if not self._is_mounted(merged):
                    self.log.emit("✅ Unmounted successfully.")
                    break
            except Exception as e:
                last_exc = e
                self.log.emit(f"ℹ️ Unmount attempt failed: {e}")

        # attempt deletion (pkexec rm -rf)
        if os.path.exists(overlay_dir):
            try:
                self.log.emit("⚡ Removing overlay directory (pkexec rm -rf)...")
                run(["pkexec", "rm", "-rf", overlay_dir], check=True)
                self.log.emit("✅ Successfully deleted overlay.")
                return True
            except Exception as e:
                self.log.emit(f"❌ pkexec deletion failed: {e}")
                # final fallback: try local removal (may require permissions)
                try:
                    shutil.rmtree(overlay_dir)
                    self.log.emit("✅ Deleted overlay via shutil.")
                    return True
                except Exception as e2:
                    self.log.emit(f"❌ Final deletion failed: {e2}")
                    return False
        else:
            self.log.emit("ℹ️ Overlay directory already removed.")
            return True

# -----------------------
# Install Dlls Worker (small)
# -----------------------
class InstallDllsWorker(QThread):
    log = pyqtSignal(str)

    def __init__(self, base_prefix: str):
        super().__init__()
        self.base = base_prefix

    def run(self):
        if shutil.which("winetricks") is None:
            self.log.emit("❌ winetricks isn't installed.")
            return
        try:
            self.log.emit("⚡ Launching winetricks (GUI)...")
            subprocess.Popen(["winetricks"], env={**os.environ, "WINEPREFIX": self.base})
            self.log.emit(f"✅ Tip: $ WINEPREFIX={self.base} winetricks")
        except Exception as e:
            self.log.emit(f"❌ Failed to start winetricks: {e}")

# -----------------------
# Temprefix worker (unified create)
# -----------------------
class TemprefixWorker(QThread):
    log = pyqtSignal(str)
    done = pyqtSignal(bool)

    def __init__(self, exe_path: str, base_prefix: str, wine_cmd:str="wine"):
        super().__init__()
        self.exe_path = exe_path
        self.base_prefix = base_prefix
        self.wine = wine_cmd

    def run(self):
        p = Prefix(3, exe_path=self.exe_path, base_prefix=self.base_prefix, wine_cmd=self.wine)
        # forward logs and done signal
        p.log.connect(self.log.emit)
        p.done.connect(self._on_done)
        p.run()  # run in same thread (Prefix is a QThread but calling run() directly keeps logic local)
        # note: we call run() directly to keep a single worker thread controlling create flow

    def _on_done(self, ok:bool):
        self.done.emit(ok)

# -----------------------
# Delete temp prefix worker (unified delete)
# -----------------------
class DeleteTempPrefixWorker(QThread):
    log = pyqtSignal(str)
    done = pyqtSignal(bool)

    def __init__(self, exe_path:str):
        super().__init__()
        self.exe_path = exe_path

    def run(self):
        p = Prefix(4, exe_path=self.exe_path)
        p.log.connect(self.log.emit)
        p.done.connect(self._on_done)
        p.run()

    def _on_done(self, ok:bool):
        self.done.emit(ok)

# -----------------------
# Analyze & Run EXE worker (unified runner with non-blocking logs)
# -----------------------
class AnalyzeAndRunExeWorker(QThread):
    log = pyqtSignal(str)
    started_signal = pyqtSignal(str)
    done = pyqtSignal(bool)

    def __init__(self, exe:str, temp_prefix_merged:str, wine_cmd:str="wine", mono_dll:Optional[str]=None):
        """
        exe: path to exe file
        temp_prefix_merged: merged dir (WINEPREFIX)
        mono_dll: optional mono dll path to prepend with 'mono' invocation
        """
        super().__init__()
        self.exe = exe
        self.wine = wine_cmd
        self.tprefix = temp_prefix_merged
        self.mono = mono_dll
        self.proc = None

    def run(self):
        env = self._build_env()
        cmd = [self.wine]
        if self.mono:
            cmd += ["mono", self.mono]
        cmd += [self.exe]
        self.started_signal.emit(f"🚀 Launching EXE: {' '.join(cmd)}")
        try:
            self.proc = subprocess.Popen(cmd, env=env, cwd=os.path.dirname(self.exe),
                                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                         text=True, bufsize=1)
        except Exception as e:
            self.log.emit(f"❌ Launch failed: {e}")
            self.done.emit(False)
            return

        self._stream_output(self.proc)
        # final status
        rc = self.proc.returncode
        if rc == 0:
            self.log.emit("✅ Execution finished successfully.")
            self.done.emit(True)
        else:
            self.log.emit(f"⚠️ EXE exited with code {rc}")
            self.done.emit(False)

    def _build_env(self):
        return {
            **os.environ,
            "WINEPREFIX": self.tprefix,
            "WINE_FULLSCREEN": "0",
            "WINEDEBUG": "+timestamp,+warn",
            "WINE_ALLOW_LARGE_ALLOCS": "1",
            "WINEESYNC": "1",
            "WINEFSYNC": "1",
            "WINEASYNC": "0",
        }

    def _stream_output(self, proc):
        q = queue.Queue()
        def reader():
            try:
                for line in iter(proc.stdout.readline, ''):
                    q.put(line.rstrip())
            finally:
                try:
                    proc.stdout.close()
                except Exception:
                    pass
        threading.Thread(target=reader, daemon=True).start()

        missing = set()
        while proc.poll() is None or not q.empty():
            try:
                line = q.get(timeout=0.1)
                if not line:
                    continue
                self.log.emit(line)
                ll = line.lower()
                if ".dll" in ll and ("cannot" in ll or "not found" in ll):
                    missing.add(line.split()[0].lower())
            except queue.Empty:
                pass
        # post-run write missing dlls log
        try:
            logs_path = os.path.join(os.path.dirname(self.exe), "Analyzable-logs.txt")
            if missing:
                with open(logs_path, "w") as f:
                    f.write("\n".join(sorted(missing)))
                self.log.emit(f"❗ Missing DLLs: {', '.join(sorted(missing))}")
            else:
                self.log.emit("✅ No missing DLLs detected.")
        except Exception:
            pass