#!/usr/bin/env python3
"""Compile, flash, and monitor this Feather using the local Arduino CLI."""
import argparse
import json
import shutil
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
CLI = str(ROOT / ".tools" / "arduino-cli") if (ROOT / ".tools" / "arduino-cli").is_file() else (shutil.which("arduino-cli") or "arduino-cli")
FQBN = "esp32:esp32:adafruit_feather_esp32_v2"


def find_feather():
    result = subprocess.run(
        [CLI, "board", "list", "--format", "json"],
        check=True, capture_output=True, text=True,
    )
    devices = json.loads(result.stdout).get("detected_ports", [])
    ports = []
    for device in devices:
        port = device.get("port", {})
        properties = port.get("properties", {})
        vid = str(properties.get("vid", "")).lower().removeprefix("0x")
        pid = str(properties.get("pid", "")).lower().removeprefix("0x")
        if vid == "1a86" and pid == "55d4" and port.get("protocol") == "serial":
            ports.append(port["address"])
    if not ports:
        sys.exit("No Feather CH9102 serial port is available. Check its USB data connection; this Mac uses Apple's built-in serial driver.")
    if len(ports) != 1:
        sys.exit("Multiple CH9102 devices found. Leave only the Feather connected before flashing.")
    return ports[0]


def run(*args):
    subprocess.run([CLI, *map(str, args)], cwd=ROOT, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["status", "flash", "scanner", "drv-test", "scan-buses", "haptics", "haptics-usb", "monitor"])
    args = parser.parse_args()
    port = find_feather()
    print("Feather:", port, flush=True)
    if args.action == "status":
        return
    sketches = {
        "flash": "first_motor_test",
        "scanner": "i2c_scanner",
        "drv-test": "drv_pair_test",
        "scan-buses": "dual_i2c_scanner",
        "haptics": "haptic_controller_wireless",
        "haptics-usb": "haptic_controller",
    }
    if args.action in sketches:
        name = sketches[args.action]
        build = ROOT / "build" / name
        run("compile", "--fqbn", FQBN, "--build-path", build, ROOT / name)
        run("upload", "--fqbn", FQBN, "--board-options", "UploadSpeed=115200", "--port", port, "--input-dir", build, ROOT / name)
    run("monitor", "--fqbn", FQBN, "--port", port, "--config", "baudrate=115200", "--timestamp")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
    except subprocess.CalledProcessError as error:
        sys.exit(error.returncode)
