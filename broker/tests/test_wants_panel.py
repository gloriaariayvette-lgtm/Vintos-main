#!/usr/bin/env python3
"""Wants DOM/action regression; every request is a stub and HOME is throwaway."""
import os, pathlib, subprocess, tempfile
root=pathlib.Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix="wants-panel-test-") as scratch:
    env=dict(os.environ,HOME=scratch,SPARK_WORKSPACE=scratch+"/workspace")
    assert env["HOME"]==scratch and env["SPARK_WORKSPACE"].startswith(scratch)
    fixture=root/"broker/tests/fixtures/wants-panel.cjs"
    assert "http://test.invalid" in fixture.read_text() and "inspection must not write to an account" in fixture.read_text()
    subprocess.run(["node",str(fixture),str(root/"clients/mobile/index.html")],env=env,check=True)
