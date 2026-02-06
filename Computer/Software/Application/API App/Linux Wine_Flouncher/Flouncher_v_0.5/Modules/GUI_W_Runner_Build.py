
import os
import shutil
import resource
import subprocess

class Utils:
    @staticmethod
    def get_ram_cpucores():
        """Returns total RAM in GB and CPU core count."""
        try:
            pages = os.sysconf('SC_PHYS_PAGES')
            page_size = os.sysconf('SC_PAGE_SIZE')
            mem_gb = (pages * page_size) / (1024**3)
            cores = os.cpu_count() or 4
            return mem_gb, cores
        except:    return 8, 4

class Build:

    @staticmethod
    def _command( exe_file, tprefix ):

        mem_gb, cores = Utils.get_ram_cpucores()

        # 1. Base & Performance Environment
        env = {**os.environ, "PYTHONUNBUFFERED": "1", "WINEPREFIX": tprefix or "", "WINEUPDATE":"0" }
        env.update({  "WINE_NO_PRELOAD": "1", "WINE_SKIP_CONFIG_CHECK": "1"  })
        
        env.update({        # 2. Scalability
            "LD_BIND_NOW": "1",
            "vblank_mode": "0",
            "WINE_NO_ASLR": "1",
            "WINE_NO_WRITE_WATCH": "1",
            "WINEDEBUG": "-all,err+all",
            "WINE_LARGE_ADDRESS_AWARE": "1",
        })

        env.update({        # 3. Rendering & Input Latency

            "WINE_FULLSCREEN_FSR_STRENGTH": "2",
            "WINE_ALLOW_MEDIUM_ADDRESS_AWARE":"1",
            "WINE_STDOUT_LINE_BUFFERED": "0", "WINE_STDERR_LINE_BUFFERED": "0",

            "DXVK_GPL": "1",
            "DXVK_ASYNC": "1",
            "DXVK_HUD": "compiler",
            "DXVK_STATE_CACHE": "1",
            "DXVK_FILTER_DEVICE_NAME": "",
            "DXVK_MAX_FRAME_LATENCY": "1",
            "STAGING_SHARED_MEMORY": "1",
            "MESA_VK_WSI_PRESENT_MODE": "immediate",
            "VK_ICD_FILENAMES": env.get("VK_ICD_FILENAMES", ""),
        })

        # 4. Dynamic Memory Tuning (Avoids OOM Crashes & Mono Lags)
        if mem_gb > 12:    env["MONO_GC_PARAMS"] = "major=marksweep-conc,nursery-size=128m,soft-heap-limit=1g"
        elif mem_gb >= 4:  env["MONO_GC_PARAMS"] = "major=marksweep-conc,nursery-size=64m,soft-heap-limit=512m"
        else:              env["MONO_GC_PARAMS"] = "nursery-size=16m,soft-heap-limit=128m"


        try:        # 5. Sync
            soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
            if hard >= 524288:
                resource.setrlimit(resource.RLIMIT_NOFILE, (hard, hard))
                env.update({
                        "WINEESYNC": "1",
                        "WINEFSYNC": "1",
                        "WINE_SYNC_IPC": "1",
                        "WINEPROXYSYNC": "1",
                        "WINE_RT_PRIO": "90",
                        "WINE_ASYNCHRONOUS_SENDMSG": "1",
                        "PULSE_LATENCY_MSEC": "60",
                    })
        except:    pass


        try:        # 6. GPU Auto-Tuner (Robust Vendor Detection)
            v_ids = ""
            for d in [f for f in os.listdir('/sys/class/drm/') if f.startswith('card')]:
                p = f'/sys/class/drm/{d}/device/vendor'
                if os.path.exists(p):
                    with open(p) as f: v_ids += f.read().lower()

            if "0x10de" in v_ids:    # NVIDIA: Low latency + Laptop support
                env.update({
                    "__GL_MaxFramesAllowed": "1",
                    "__GL_THREADED_OPTIMIZATIONS": "1",
                    "__GL_SHADER_DISK_CACHE_SIZE":"1024",
                    "__GL_SHADER_DISK_CACHE_SKIP_CLEANUP":"1",
                    "__NV_PRIME_RENDER_OFFLOAD": "1",
                    "__VK_LAYER_NV_optimus": "NVIDIA_only"
                })
            if "0x1002" in v_ids:   # AMD
                env.update({"mesa_glthread": "true", "RADV_PERFTEST": "gpl,sam", "AMD_DEBUG": "precompile"})
            if "0x8086" in v_ids:   # Intel
                env.update({"mesa_glthread": "true", "INTEL_DEBUG": "noccs"})

        except:    pass


        boosters = []        # 7. Command Assembler

        if shutil.which("ionice"): boosters = ["ionice", "-c", "2", "-n", "0"]

        if cores > 2 and shutil.which("taskset"):    # 8. Prioritizing Core Affinity
            mask = "0xFE" if cores > 8 else hex((1 << cores) - 2)
            boosters += ["taskset", mask]

        cmd = boosters + ["wine", exe_file]        # 9. Assemble final command
        
        return cmd, env

