# workers_refactored_v2.py
import os, time, queue, threading, subprocess, shutil
from PyQt5.QtCore import QThread, pyqtSignal

# -------------------------
# Utility: subprocess runner
# -------------------------
def _run(cmd, check=True, capture_output=False, env=None, cwd=None, text=True):
    try:
        return subprocess.run(cmd, check=check, capture_output=capture_output, env=env, cwd=cwd, text=text)
    except subprocess.CalledProcessError as e:
        return e

# -------------------------
# Minimal job class (unchanged)
# -------------------------
class CJob:
    def __init__(self, num, path, obj_name):
        self.num = num
        self.path = path
        self.obj_name = obj_name

    def analyze(self):
        full_path = os.path.join(self.path, self.obj_name)
        if self.num == 0: return os.path.isdir(full_path)
        if self.num == 1: return os.path.isfile(full_path)
        return None

# -------------------------
# Prefix manager (create/init/delete) - refactored
# -------------------------
class Prefix(QThread):
    log = pyqtSignal(str)
    done = pyqtSignal(bool)

    def __init__(self, action:int, exe_path=None, base_prefix=None, wine_cmd="wine"):
        """
        action: 3 => create, 4 => delete
        exe_path: folder where .wine_temp_noverlay will be created
        base_prefix: lowerdir for overlay
        """
        super().__init__()
        self.action = action
        self.exe_path = exe_path
        self.base_prefix = base_prefix
        self.wine = wine_cmd

    def run(self):
        try:
            if self.action == 3:
                self.done.emit(bool(self._create_temp_prefix()))
            elif self.action == 4:
                self.done.emit(bool(self._delete_temp_prefix()))
            else:
                self.log.emit("❌ No Prefix Action Taken."); self.done.emit(False)
        except Exception as e:
            self.log.emit(f"❌ Prefix thread error: {e}")
            self.done.emit(False)

    # ---- create ----
    def _create_temp_prefix(self):
        if not self.exe_path or not self.base_prefix:
            self.log.emit("❌ Missing exe_path or base_prefix."); return False

        overlay_dir = os.path.join(self.exe_path, ".wine_temp_noverlay")
        dirs = {p: os.path.join(overlay_dir, p) for p in ("upper","work","merged")}
        try:
            for d in dirs.values(): os.makedirs(d, exist_ok=True)
        except OSError as e:
            self.log.emit(f"❌ Failed to prepare overlay dirs: {e}"); return False

        if not self._mount_overlay(dirs["merged"], overlay_dir): return False
        if not self._prepare_merged_dirs(dirs["merged"]): return False
        return self._init_wine_prefix(dirs["merged"])

    def _mount_overlay(self, merged, overlay_dir):
        lower = self.base_prefix
        native_cmd = ["pkexec","mount","-t","overlay","overlay","-o",
                      f"lowerdir={lower},upperdir={overlay_dir}/upper,workdir={overlay_dir}/work", merged]
        fuse_cmd = ["fuse-overlayfs","-o",f"lowerdir={lower},upperdir={overlay_dir}/upper,workdir={overlay_dir}/work", merged]

        for cmd, label in ((native_cmd,"native"),(fuse_cmd,"fuse")):
            try: self.log.emit(f"Mounting ({label}): {' '.join(cmd)}"); _run(cmd); self.log.emit("✅ Overlay Mounted."); return True
            except Exception as e: self.log.emit(f"⚠️ Mount failed ({label}): {e}"); continue
        self.log.emit("❌ All overlay mount attempts failed."); return False

    def _prepare_merged_dirs(self, merged):
        try: os.makedirs(os.path.join(merged,"drive_c","windows"), exist_ok=True); return True
        except OSError as e: self.log.emit(f"❌ Failed preparing merged dirs: {e}"); return False

    def _init_wine_prefix(self, merged):
        env = {**os.environ,"WINEPREFIX":merged,"WINEARCH":"win64","WINEDEBUG":"-all","WINEUPDATE":"0","WINEDLLOVERRIDES":"dll=ignore"}
        try:
            self.log.emit("⚡ Initializing Wine prefix...")
            _run([self.wine,"wineboot","-u"], env=env, cwd=os.path.dirname(self.exe_path))
            # ensure Win10 registry
            reg_check = _run([self.wine,"reg","query","HKCU\\Software\\Wine\\Wine\\Config","/v","Version"], env=env, capture_output=True)
            if "Version" not in getattr(reg_check,"stdout",""):
                _run([self.wine,"reg","add","HKCU\\Software\\Wine\\Wine\\Config","/v","Version","/d","10.0","/f"], env=env)
            self.log.emit("✅ Wine prefix ready (Win10)."); return True
        except Exception as e: self.log.emit(f"❌ Failed Wine init: {e}"); return False

    # ---- delete ----
    def _delete_temp_prefix(self):
        overlay_dir = os.path.join(self.exe_path,".wine_temp_noverlay")
        merged = os.path.join(overlay_dir,"merged")
        if not os.path.exists(overlay_dir): self.log.emit("ℹ️ No temp prefix found."); return True

        if not self._is_mounted(merged):
            return self._safe_remove(overlay_dir)
        return self._unmount_and_remove(merged, overlay_dir)

    def _is_mounted(self, merged):
        try: return merged in _run(["mount"], capture_output=True).stdout
        except Exception: return False

    def _unmount_and_remove(self, merged, overlay_dir):
        for cmd,label in [(["fusermount","-u",merged],"fusermount"),(["pkexec","umount","-l",merged],"pkexec umount"),(["pkexec","umount",merged],"pkexec")]:
            try: self.log.emit(f"Attempting unmount ({label})"); _run(cmd); time.sleep(0.1); 
            except Exception as e: self.log.emit(f"⚠️ {label} failed: {e}"); continue
            if not self._is_mounted(merged): return self._safe_remove(overlay_dir)
        try: self.log.emit("Attempting forced deletion..."); _run(["pkexec","rm","-rf",overlay_dir]); return True
        except Exception as e: self.log.emit(f"❌ Forced deletion failed: {e}"); return self._safe_remove(overlay_dir)

    def _safe_remove(self, path):
        try: shutil.rmtree(path) if os.path.exists(path) else None; self.log.emit("✅ Deleted temp prefix."); return True
        except Exception as e: self.log.emit(f"❌ Deletion failed: {e}"); return False

# -------------------------
# RunAnalyze worker (non-blocking EXE)
# -------------------------
class RunAnalyze(QThread):
    log = pyqtSignal(str)
    done = pyqtSignal(bool)

    def __init__(self, exe_path, exe_file, tprefix_path=None, BepInEx_dll=None, wine_cmd="wine"):
        super().__init__()
        self.wine,self.exe_file,self.tprefix_path,self.BepInExEx_dll = wine_cmd,exe_file,tprefix_path,BepInEx_dll
        self.proc=None

    def run(self):
        try: cmd,env = self._build_command(); self._launch_exe(cmd,env)
        except Exception as e: self.log.emit(f"❌ Run error: {e}"); self.done.emit(False)

    def _build_command(self):
        env={**os.environ,"WINEPREFIX":self.tprefix_path or "",
             "WINE_FULLSCREEN":"0","WINEDEBUG":"+timestamp,+warn","WINE_ALLOW_LARGE_ALLOCS":"1",
             "WINEESYNC":"1","WINEFSYNC":"1","WINEASYNC":"0"}
        cmd=[self.wine]; 
        if self.BepInExEx_dll: cmd+=["mono",self.BepInExEx_dll]
        cmd+=[self.exe_file]
        return cmd, env

    def _launch_exe(self, cmd, env):
        self.log.emit(f"🚀 Launching EXE: {' '.join(cmd)}")
        try:
            self.proc=subprocess.Popen(cmd,env=env,cwd=os.path.dirname(self.exe_file),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
        except Exception as e: self.log.emit(f"❌ Launch failed: {e}"); self.done.emit(False); return
        self._monitor_proc(self.proc)

    def _monitor_proc(self, proc):
        q = queue.Queue()
        threading.Thread(target=lambda: [q.put(l.rstrip()) for l in iter(proc.stdout.readline,'')] and proc.stdout.close(), daemon=True).start()
        missing=set()
        while proc.poll() is None or not q.empty():
            try:
                line = q.get(timeout=0.1)
                if not line: continue
                self.log.emit(line)
                if ".dll" in line.lower() and any(x in line.lower() for x in ("not found","cannot","error")): missing.add(line.split()[0].lower())
            except queue.Empty: pass
        try:
            if missing:
                with open(os.path.join(os.path.dirname(self.exe_file),"Analyzable-logs.txt"),"w") as f: f.write("\n".join(sorted(missing)))
                self.log.emit(f"❗ Missing DLLs: {', '.join(sorted(missing))}")
            else: self.log.emit("✅ No missing DLLs detected.")
        except: pass
        self.done.emit(proc.returncode==0)

# -------------------------
# Winetricks launcher
# -------------------------
class InstallDllsWorker(QThread):
    log = pyqtSignal(str)
    def __init__(self, base, wine_cmd="wine"):
        super().__init__(); self.base,self.wine=base,wine_cmd
    def run(self):
        if shutil.which("winetricks") is None: self.log.emit("❌ winetricks isn't installed."); return
        try: self.log.emit("⚡ Launching Winetricks..."); subprocess.Popen(["winetricks"], env={**os.environ,"WINEPREFIX":self.base}); self.log.emit(f"✅ Tip: $ WINEPREFIX={self.base} winetricks")
        except Exception as e: self.log.emit(f"❌ Failed to start winetricks: {e}")