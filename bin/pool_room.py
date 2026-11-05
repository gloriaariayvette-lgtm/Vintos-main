#!/usr/bin/env python3
"""room: one machine's free room, as JSON. Read-only; loads nothing, starts nothing.

Run on each machine in the pool (over the existing SSH access). The router reads this before choosing where a
model call goes. Unknown readings are reported as null, never guessed.

    python3 room.py
"""
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import urllib.request

GiB = 1024 ** 3


def run(args, timeout=10):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout).stdout
    except Exception:
        return ''


def mac_memory():
    total = int(run(['sysctl', '-n', 'hw.memsize']) or 0)
    vm = run(['vm_stat'])
    page = int((re.search(r'page size of (\d+)', vm) or [0, 16384])[1])
    pages = lambda name: int((re.search(name + r':\s+(\d+)', vm) or [0, 0])[1])
    # free + inactive + purgeable + speculative is what macOS can hand out without pressure
    avail = (pages('Pages free') + pages('Pages inactive') + pages('Pages purgeable') + pages('Pages speculative')) * page
    return total, avail


def wsl_windows_memory():
    # inside WSL the Linux numbers describe the WSL VM, not the machine; ask Windows
    out = run(['powershell.exe', '-NoProfile', '-Command',
               '$o=Get-CimInstance Win32_OperatingSystem; "$($o.TotalVisibleMemorySize) $($o.FreePhysicalMemory)"'])
    try:
        t, f = out.split()
        return int(t) * 1024, int(f) * 1024
    except ValueError:
        return None, None


def linux_memory():
    info = open('/proc/meminfo').read()
    k = lambda name: int(re.search(name + r':\s+(\d+)', info)[1]) * 1024
    return k('MemTotal'), k('MemAvailable')


def nvidia():
    exe = shutil.which('nvidia-smi') or shutil.which('nvidia-smi.exe') or '/mnt/c/Windows/System32/nvidia-smi.exe'
    out = run([exe, '--query-gpu=name,memory.used,memory.total,utilization.gpu', '--format=csv,noheader,nounits'])
    gpus = []
    for line in out.strip().splitlines():
        try:
            name, used, total, util = [x.strip() for x in line.split(',')]
            gpus.append(dict(name=name, used_bytes=int(used) * 1024 ** 2, total_bytes=int(total) * 1024 ** 2,
                             free_bytes=(int(total) - int(used)) * 1024 ** 2, busy_percent=int(util)))
        except ValueError:
            pass
    return gpus


def lmstudio_loaded():
    lms = os.path.expanduser('~/.lmstudio/bin/lms')
    if not os.path.exists(lms):
        lms = shutil.which('lms') or '/mnt/c/Users/glori/.lmstudio/bin/lms.exe'
    out = run([lms, 'ps'])
    rows = []
    for line in out.splitlines()[1:]:
        cols = line.split()
        if cols and not line.startswith('IDENTIFIER'):
            rows.append(cols[0])
    return rows


def llama_servers():
    # our own pool servers, if any are running on the usual ports
    found = []
    for port in (8840, 8841):
        try:
            with urllib.request.urlopen('http://127.0.0.1:%d/v1/models' % port, timeout=2) as r:
                found += [dict(port=port, model=m['id']) for m in json.load(r).get('data', [])]
        except Exception:
            pass
    return found


def main():
    system = platform.system()
    wsl = 'microsoft' in platform.release().lower()
    if system == 'Darwin':
        total, avail = mac_memory()
        unified = True
    elif wsl:
        total, avail = wsl_windows_memory()
        unified = False
    else:
        total, avail = linux_memory()
        unified = False
    load = os.getloadavg()[0] if hasattr(os, 'getloadavg') else None
    print(json.dumps(dict(
        host=socket.gethostname(),
        system='Windows (WSL)' if wsl else system,
        cpus=os.cpu_count(),
        load_1min=load,
        memory=dict(total_bytes=total, available_bytes=avail, unified_with_gpu=unified),
        gpus=[] if system == 'Darwin' else nvidia(),
        lmstudio_loaded=lmstudio_loaded(),
        pool_servers=llama_servers(),
    ), indent=2))


if __name__ == '__main__':
    main()
