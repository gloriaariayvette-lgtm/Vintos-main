"""OS-enforced scratch execution. Missing isolation is an error, never a fallback."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import signal, tempfile
import sys


def run(argv, scratch, *, read_roots=(), timeout=60, loopback=False, broker=None, listener=None):
    if os.environ.get("VINTOS_TEST_SANDBOX_BROKER"):
        import time, uuid
        queue=Path(os.environ["VINTOS_TEST_SANDBOX_BROKER"])
        identity=uuid.uuid4().hex
        request=queue/(identity+".request")
        request.write_text(json.dumps({"argv":list(map(str,argv)),"scratch":str(scratch),"timeout":min(timeout,180)}))
        response=queue/(identity+".response")
        deadline=time.monotonic()+timeout+10
        while not response.exists():
            if time.monotonic()>deadline: raise TimeoutError("sandbox broker did not respond")
            time.sleep(.05)
        result=json.loads(response.read_text())
        if "error" in result: raise RuntimeError(result["error"])
        return subprocess.CompletedProcess(argv, result["returncode"], result["stdout"], result["stderr"])
    if not loopback:
        limiter="import os,sys,resource; resource.setrlimit(resource.RLIMIT_FSIZE,(16777216,16777216)); resource.setrlimit(resource.RLIMIT_CPU,(60,60)); os.execv(sys.argv[1],sys.argv[1:])"
        argv=[sys.executable,"-c",limiter,*map(str,argv)]
    scratch = str(Path(scratch).resolve())
    roots = {str(Path(p).resolve()) for p in read_roots}
    roots.update(str(Path(p).resolve()) for p in (sys.prefix, sys.base_prefix))
    env = {"HOME": scratch, "TMPDIR": scratch, "TMP": scratch, "TEMP": scratch,
           "PATH": os.path.dirname(sys.executable) + os.pathsep + os.defpath, "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1",
           "SPARK_WORKSPACE": os.path.join(scratch, "workspace")}
    if listener is not None:
        env["VINTOS_TEST_LISTENER_FD"]=str(listener.fileno())
        env["VINTOS_TEST_PORT"]=str(listener.getsockname()[1])
    if broker: env["VINTOS_TEST_SANDBOX_BROKER"]=str(broker)
    if sys.platform == "darwin" and shutil.which("sandbox-exec"):
        # No arbitrary home read: credentials cannot enter a generated process.
        allowed = roots | {scratch}
        profile = '(version 1)(allow default)(deny network*)'
        if not loopback: profile += '(deny process-fork)'
        profile += '(deny file-write* (require-all (require-not (subpath %s)) (require-not (literal "/dev/null"))))' % json.dumps(scratch)
        for protected in {str(Path.home().resolve()), "/Users", "/private/tmp", "/tmp", "/private/var/folders", "/var/folders"}:
            profile += '(deny file-read-data (require-all (subpath %s) %s))' % (
                json.dumps(protected),
                ' '.join('(require-not (subpath %s))' % json.dumps(p) for p in allowed))
        if loopback:
            profile += '(allow network* (subpath %s))' % json.dumps(scratch)
        if listener is not None:
            port=listener.getsockname()[1]
            profile += '(allow network* (local ip "localhost:%d") (remote ip "localhost:%d"))' % (port,port)
        command = ["/usr/bin/sandbox-exec", "-p", profile, *map(str, argv)]
    elif sys.platform.startswith("linux") and shutil.which("bwrap"):
        command = ["bwrap", "--die-with-parent", "--new-session", "--unshare-all", "--proc", "/proc", "--dev", "/dev"]
        # Debian/Ubuntu BLAS and LAPACK resolve through /etc/alternatives.
        # Expose those system-library links read-only, not the rest of /etc.
        for p in sorted(roots | {"/usr", "/bin", "/sbin", "/lib", "/lib64", "/etc/ld.so.cache", "/etc/alternatives"}):
            if os.path.exists(p): command += ["--ro-bind", p, p]
        command += ["--bind", scratch, scratch, "--chdir", scratch, *map(str, argv)]
    else:
        raise RuntimeError("PRECONDITION OS_ISOLATION_MISSING: Linux needs bubblewrap (sudo apt-get update && sudo apt-get install -y bubblewrap); macOS needs sandbox-exec. Execution refused without OS isolation")
    # Reap the entire child process group, including descendants left after a
    # successful test. Capture to files rather than unbounded in-memory pipes.
    with tempfile.TemporaryFile(dir=scratch) as stdout, tempfile.TemporaryFile(dir=scratch) as stderr:
        process=subprocess.Popen(command,cwd=scratch,env=env,stdout=stdout,stderr=stderr,
                                 start_new_session=True,pass_fds=((listener.fileno(),) if listener is not None else ()))
        try:
            process.wait(timeout=timeout)
        finally:
            try: os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError: pass
            process.wait()
        stdout.seek(0);stderr.seek(0)
        return subprocess.CompletedProcess(argv,process.returncode,stdout.read(2*1024*1024).decode("utf-8","replace"),stderr.read(2*1024*1024).decode("utf-8","replace"))
