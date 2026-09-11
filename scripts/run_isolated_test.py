#!/usr/bin/env python3
"""Run a repository test against copies, a fresh home, and an OS boundary."""
from pathlib import Path
import shutil
import sys
import tempfile
import threading, json, time, os, socket
from isolated_exec import run


def main():
    test = Path(sys.argv[1]).resolve()
    repo = Path(__file__).resolve().parents[1]
    relative = test.relative_to(repo)
    with tempfile.TemporaryDirectory(prefix="vs-", dir="/tmp") as tmp:
        root = Path(tmp)
        for name in (repo.name, "plithra-app", "vintos-app"):
            src = repo if name == repo.name else repo.parent / name
            if src.is_dir():
                shutil.copytree(src, root / name, symlinks=True,
                                ignore=shutil.ignore_patterns(".git", "__pycache__", "node_modules", ".venv"))
        copied = root / repo.name
        (root / ".vintos/workspace/memory").mkdir(parents=True)
        (root / "workspace/memory").mkdir(parents=True)
        # Copy path is the only checkout the child may read or write.
        bootstrap = "import os,sys,runpy; os.environ.pop('SPARK_WORKSPACE',None); sys.path.insert(0,sys.argv[1]); sys.argv=sys.argv[2:]; __import__('test_http_fixture').install(); runpy.run_path(sys.argv[0],run_name='__main__')"
        # macOS cannot stack sandbox profiles. A trusted parent launches nested
        # generated-code tests with a stricter sandbox through a scratch-only queue.
        queue=root/"sandbox-requests";queue.mkdir()
        stop=threading.Event()
        def serve():
            seen=set()
            while not stop.wait(.05):
                for request in queue.glob("*.request"):
                    if request.name in seen: continue
                    try: payload=json.loads(request.read_text())
                    except (ValueError,OSError): continue
                    seen.add(request.name)
                    response=request.with_suffix(".response")
                    try:
                        scratch=Path(payload["scratch"]).resolve()
                        if scratch==root.resolve() or not scratch.is_relative_to(root.resolve()):
                            raise ValueError("child scratch must be strictly inside suite scratch")
                        argv=payload["argv"]
                        if not argv or Path(argv[0]).resolve()!=Path(sys.executable).resolve():
                            raise ValueError("only the configured interpreter is accepted")
                        child=run(argv,scratch,timeout=min(float(payload["timeout"]),180))
                        data={"returncode":child.returncode,"stdout":child.stdout,"stderr":child.stderr}
                    except Exception as exc:data={"error":str(exc)}
                    response.write_text(json.dumps(data))
        worker=threading.Thread(target=serve,daemon=True);worker.start()
        listener=None
        if sys.platform=="darwin":
            listener=socket.socket();listener.bind(("127.0.0.1",0))
        try:
            result = run([sys.executable, "-c", bootstrap, str(copied / "scripts"), str(copied / relative)], root,
                         timeout=180, loopback=True, broker=queue if sys.platform=="darwin" else None, listener=listener)
        finally:
            stop.set();worker.join(timeout=190)
            if listener is not None: listener.close()
        print(result.stdout, end="")
        print(result.stderr, end="", file=sys.stderr)
        return result.returncode


if __name__ == "__main__":
    try: sys.exit(main())
    except Exception as exc:
        print("isolated test refused:", exc, file=sys.stderr)
        sys.exit(1)
