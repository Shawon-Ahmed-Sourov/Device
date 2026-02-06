
import os
import pty
import signal
import subprocess
from PyQt5.QtCore import QThread, pyqtSignal

from GUI_W_Runner_Build import Build

class RunAnalyze(QThread):
    log = pyqtSignal(str)
    done = pyqtSignal(bool)

    def __init__(self, exe_path, exe_file):
        super().__init__()
        self.exe_path = os.path.abspath(exe_path)
        self.exe_file = os.path.abspath(exe_file)
        self.tprefix  = os.path.join(self.exe_path, ".wine_temp_noverlay", "merged")
        self.proc = None

    def run(self):

        master = None
        try:

            cmd, env = Build._command(self.exe_file, self.tprefix)

            self.log.emit(f"📂 Temporary Prefix At:{self.tprefix}")
            self.log.emit(f"⚡ Launching : {' '.join(cmd)}\n")
            master = self._start_process(cmd, env, self.exe_path)
        
            success = self._read_logs(master)   
            self.done.emit(success)

        except Exception as e:  self.log.emit(f"❌ Failure: {str(e)}") ; self.done.emit(False)
        finally:    self._cleanup(master) # 4. Final Cleanup


    def _start_process(self, cmd, env, cwd):
        master, slave = pty.openpty()
        
        self.proc = subprocess.Popen(
            cmd, env=env, cwd=cwd,
            text=True, 
            preexec_fn=os.setsid,  # Creates a process group for clean cleanup
            stdout=slave, 
            stderr=slave, 
            stdin=slave,
            close_fds=True
        )
        os.close(slave)  # Close slave in parent; proc uses it
        return master

    def _read_logs(self, master):
        try:
            with os.fdopen(master, 'r', errors='ignore', closefd=False) as f:
                while True:
                    line = f.readline()
                    if line:     self.log.emit(line.strip())
                    if not line and self.proc.poll() is not None:    break
        except OSError:    pass # Normal PTY closure
    
        ret = self.proc.wait() 
        self.log.emit(f"\n⏹️ Process Closed with code: {ret}")
        return ret == 0

    def _cleanup(self, master):

        if master:
            try:    os.close(master)
            except OSError:    pass

        if self.proc and self.proc.poll() is None:
            try:
                pgid = os.getpgid(self.proc.pid)
                for sig in [signal.SIGTERM, signal.SIGKILL]:
                    try:
                        os.killpg(pgid, sig)
                        self.proc.wait(timeout=2)
                        break
                    except (subprocess.TimeoutExpired, ProcessLookupError):    continue
            except Exception:    pass

