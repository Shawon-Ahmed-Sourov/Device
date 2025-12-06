# workers_best.py
import os, time, queue, threading, subprocess, shutil
from PyQt5.QtCore import QThread, pyqtSignal

# -------------------------
# Utility: safe subprocess runner
# -------------------------
def _run(cmd, **kwargs):
    try: return subprocess.run(cmd, check=True, **kwargs)
    except subprocess.CalledProcessError as e: return e

# -------------------------
# Minimal Job
# -------------------------
class CJob:
    def __init__(self, num, path, obj_name):
        self.num, self.path, self.obj_name = num, path, obj_name
    def analyze(self):
        full = os.path.join(self.path, self.obj_name)
        return os.path.isdir(full) if self.num==0 else os.path.isfile(full) if self.num==1 else None

# -------------------------
# Prefix manager: create / delete / init
# -------------------------
class Prefix(QThread):
    log = pyqtSignal(str)
    done = pyqtSignal(bool)
    
    def __init__(self, action:int, exe_path=None, base_prefix=None, wine_cmd="wine"):
        super().__init__()
        self.action, self.exe_path, self.base_prefix, self.wine = action, exe_path, base_prefix, wine_cmd

    def run(self):
        try:
            if self.action==3: self.done.emit(bool(self._create_prefix()))
            elif self.action==4: self.done.emit(bool(self._delete_prefix()))
            else: self.log.emit("❌ No Prefix Action."); self.done.emit(False)
        except Exception as e: self.log.emit(f"❌ Prefix error: {e}"); self.done.emit(False)

    # ---- create ----
    def _create_prefix(self):
        if not self.exe_path or not self.base_prefix: self.log.emit("❌ Missing paths."); return False
        overlay = os.path.join(self.exe_path,".wine_temp_noverlay")
        dirs = {p: os.path.join(overlay,p) for p in ("upper","work","merged")}
        try: [os.makedirs(d, exist_ok=True) for d in dirs.values()]
        except OSError as e: self.log.emit(f"❌ Overlay dirs fail: {e}"); return False
        if not self._mount_overlay(dirs["merged"], overlay): return False
        if not self._prepare_merged_dirs(dirs["merged"]): return False
        return self._init_wine(dirs["merged"])

    def _mount_overlay(self, merged, overlay):
        cmds = [
            (["pkexec","mount","-t","overlay","overlay","-o",
              f"lowerdir={self.base_prefix},upperdir={overlay}/upper,workdir={overlay}/work", merged], "native"),
            (["fuse-overlayfs","-o",f"lowerdir={self.base_prefix},upperdir={overlay}/upper,workdir={overlay}/work", merged], "fuse")
        ]
        for cmd,label in cmds:
            try: self.log.emit(f"Mounting ({label})"); _run(cmd, capture_output=True, text=True); self.log.emit("✅ Mounted"); return True
            except Exception as e: self.log.emit(f"⚠️ {label} fail: {e}")
        self.log.emit("❌ All overlay mounts failed"); return False

    def _prepare_merged_dirs(self, merged):
        try: os.makedirs(os.path.join(merged,"drive_c","windows"), exist_ok=True); return True
        except OSError as e: self.log.emit(f"❌ Drive dirs fail: {e}"); return False

    def _init_wine(self, merged):
        env = {**os.environ,"WINEPREFIX":merged,"WINEARCH":"win64","WINEDEBUG":"-all","WINEUPDATE":"0","WINEDLLOVERRIDES":"dll=ignore"}
        try:
            self.log.emit("⚡ Initializing Wine...")
            _run([self.wine,"wineboot","-u"], env=env, cwd=os.path.dirname(self.exe_path))
            reg_check = _run([self.wine,"reg","query","HKCU\\Software\\Wine\\Wine\\Config","/v","Version"], env=env, capture_output=True, text=True)
            if "Version" not in getattr(reg_check,"stdout",""):
                _run([self.wine,"reg","add","HKCU\\Software\\Wine\\Wine\\Config","/v","Version","/d","10.0","/f"], env=env)
            self.log.emit("✅ Wine prefix ready (Win10)"); return True
        except Exception as e: self.log.emit(f"❌ Wine init fail: {e}"); return False

    # ---- delete ----
    def _delete_prefix(self):
        overlay = os.path.join(self.exe_path,".wine_temp_noverlay")
        merged = os.path.join(overlay,"merged")
        if not os.path.exists(overlay): self.log.emit("ℹ️ No prefix found"); return True
        if not self._is_mounted(merged): return self._safe_remove(overlay)
        return self._unmount_remove(merged, overlay)

    def _is_mounted(self, merged):
        try: return merged in _run(["mount"], capture_output=True, text=True).stdout
        except: return False

    def _unmount_remove(self, merged, overlay):
        for cmd,label in [(["fusermount","-u",merged],"fusermount"),(["pkexec","umount","-l",merged],"pkexec umount"),(["pkexec","umount",merged],"pkexec")]:
            try: self.log.emit(f"Unmount ({label})"); _run(cmd, capture_output=True, text=True); time.sleep(0.1)
            except Exception as e: self.log.emit(f"⚠️ {label} fail: {e}"); continue
            if not self._is_mounted(merged): return self._safe_remove(overlay)
        try: self.log.emit("Forced delete"); _run(["pkexec","rm","-rf",overlay]); return True
        except Exception as e: self.log.emit(f"❌ Force delete fail: {e}"); return self._safe_remove(overlay)

    def _safe_remove(self, path):
        try: shutil.rmtree(path) if os.path.exists(path) else None; self.log.emit("✅ Deleted"); return True
        except Exception as e: self.log.emit(f"❌ Remove fail: {e}"); return False

# -------------------------
# RunAnalyze: launch EXE with live logs
# -------------------------
class RunAnalyze(QThread):
    log = pyqtSignal(str)
    done = pyqtSignal(bool)
    def __init__(self, exe_path, exe_file, tprefix=None, BepInEx_dll=None, wine_cmd="wine"):
        super().__init__()
        self.wine,self.exe_file,self.tprefix,self.BepInEx_dll=wine_cmd,exe_file,tprefix,BepInEx_dll
        self.proc=None

    def run(self):
        try: cmd,env=self._build_cmd(); self._launch(cmd,env)
        except Exception as e: self.log.emit(f"❌ Run error: {e}"); self.done.emit(False)

    def _build_cmd(self):
        env={**os.environ,"WINEPREFIX":self.tprefix or "","WINE_FULLSCREEN":"0","WINEDEBUG":"+timestamp,+warn","WINE_ALLOW_LARGE_ALLOCS":"1","WINEESYNC":"1","WINEFSYNC":"1","WINEASYNC":"0"}
        cmd=[self.wine]+(["mono",self.BepInEx_dll] if self.BepInEx_dll else [])+[self.exe_file]
        return cmd, env

    def _launch(self, cmd, env):
        self.log.emit(f"🚀 Launch: {' '.join(cmd)}")
        try: self.proc=subprocess.Popen(cmd, env=env, cwd=os.path.dirname(self.exe_file), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        except Exception as e: self.log.emit(f"❌ Launch fail: {e}"); self.done.emit(False); return
        self._monitor(self.proc)

    def _monitor(self, proc):
        q=queue.Queue()
        def reader(): 
            try: 
                for l in iter(proc.stdout.readline,''): q.put(l.rstrip())
            finally: 
                try: proc.stdout.close()
                except: pass
        threading.Thread(target=reader,daemon=True).start()
        missing=set()
        while proc.poll() is None or not q.empty():
            try:
                line=q.get(timeout=0.1)
                if not line: continue
                self.log.emit(line)
                if ".dll" in line.lower() and any(x in line.lower() for x in ("not found","cannot","error")): missing.add(line.split()[0].lower())
            except queue.Empty: pass
        if missing:
            try:
                with open(os.path.join(os.path.dirname(self.exe_file),"Analyzable-logs.txt"),"w") as f: f.write("\n".join(sorted(missing)))
                self.log.emit(f"❗ Missing DLLs: {', '.join(sorted(missing))}")
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
        if shutil.which("winetricks") is None: self.log.emit("❌ winetricks missing"); return
        try: self.log.emit("⚡ Launching Winetricks..."); subprocess.Popen(["winetricks"], env={**os.environ,"WINEPREFIX":self.base}); self.log.emit(f"✅ Tip: $ WINEPREFIX={self.base} winetricks")
        except Exception as e: self.log.emit(f"❌ Winetricks fail: {e}")