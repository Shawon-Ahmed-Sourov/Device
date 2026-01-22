
import os, pty, signal, subprocess
from PyQt5.QtCore import QThread, pyqtSignal

from GUI_W_CTask import Build

class CmnUtils:

    @staticmethod
    def start_process(cmd, env, cwd):

        master, slave = pty.openpty()
        proc = subprocess.Popen(
            cmd, env=env, cwd=cwd,
            text=True, preexec_fn=os.setsid,  # Creates a process group for clean cleanup
            stdout=slave, stderr=slave, stdin=slave,    close_fds=True
        )
        os.close(slave)
        return proc, master

    @staticmethod
    def cleanup(proc, master):

        if master:
            try:    os.close(master)
            except OSError:    pass

        if proc and proc.poll() is None:
            try:
                pgid = os.getpgid(proc.pid)
                for sig in [signal.SIGTERM, signal.SIGKILL]:
                    try:   os.killpg(pgid, sig) ; proc.wait(timeout=2) ; break
                    except (subprocess.TimeoutExpired, ProcessLookupError):    continue
            except Exception:  pass


class RunAnalyze(QThread):

    log = pyqtSignal(str) ; done = pyqtSignal(bool)

    def __init__(self, exe_path, exe_file):
        super().__init__()
        self.exe_path = os.path.abspath(exe_path)
        self.exe_file = os.path.abspath(exe_file)
        self.tprefix_path = os.path.join(self.exe_path, ".wine_temp_noverlay", "merged")
        self.proc = None

    def run(self):    # The Main Orchestrator.
 
        master = None
        try:
         # 1. Prepare Command
            cmd, env = Build._command( self.exe_file, self.tprefix_path)
            self.log.emit(f"⚡ Launching : {' '.join(cmd)}")
            
         # 2. Launch
            self.proc, master = CmnUtils.start_process( cmd, env, self.exe_path)
        
         # 3. Monitor
            success = self._realTime_logs(master)   

            self.done.emit(success)

        except Exception as e: self.log.emit(f"❌ Failure: {str(e)}") ; self.done.emit(False)
        finally:               CmnUtils.cleanup(self.proc, master)  # 4.Final Cleanup

    def _realTime_logs(self, master):
        try:
            with os.fdopen(master, 'r', errors='ignore', closefd=False) as f:
                while True:
                    line = f.readline()
                    if line: self.log.emit(line.strip())
                    if not line and self.proc.poll() is not None: break
        except OSError: pass # Normal PTY closure
    
        # Logic after the loop ends
        ret = self.proc.wait() 
        self.log.emit(f"\n⏹️ Process Closed with code: {ret}")
        return ret == 0

