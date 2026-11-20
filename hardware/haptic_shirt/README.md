# Haptic shirt controller and Mac bridge

ESP32 Feather V2 controls twelve independent PCA9685/MOSFET motors and two DRV2605L pairs (chest and shoulder blades). The specialized chest and back motors are best for looping. The loop option repeats a pattern for **three minutes (180 seconds)** and then stops automatically.

This directory contains the firmware, local USB/Bluetooth adapters, live-only prompt generator, saved body-zone map, and offline tests. It does not register a live Vintos action or install a service on Aegis.

## Setup on the Mac

Use Python 3.12:

```sh
python3.12 -m venv .blevenv
.blevenv/bin/python -m pip install -r ble-requirements.lock
```

Install Arduino CLI on PATH, the ESP32 core, Adafruit PWM Servo Driver, and Adafruit DRV2605 Library. Board FQBN: `esp32:esp32:adafruit_feather_esp32_v2`. Upload at 115200 baud. `python3 feather.py haptics` builds/uploads wireless firmware over USB; `haptics-usb` selects the USB-only rollback controller. Pair once with `.blevenv/bin/python shirt_ble.py pair`; the device's generated pairing code is available through the USB setup command `paircode`.

## Controls

```sh
.blevenv/bin/python shirt_ble.py motor right_wrist
.blevenv/bin/python shirt_ble.py arm right out --pace slow
.blevenv/bin/python shirt_ble.py arm left in --pace normal
.blevenv/bin/python shirt_ble.py pattern chest wave --loop --peak 20
.blevenv/bin/python shirt_ble.py pattern back wave3 --loop --peak 10
.blevenv/bin/python shirt_ble.py pattern both soft --loop --peak 10
.blevenv/bin/python shirt_ble.py signal three_taps --pair chest --loop
.blevenv/bin/python shirt_ble.py stop
.blevenv/bin/python shirt_ble.py context
```

`--loop` always means 180 seconds. Without it, usual patterns default to five seconds; `--seconds` permits a bounded single request up to 30 seconds. `--loop` and `--seconds` are mutually exclusive. The four authored signals can also repeat for three minutes. Individual motor controls and arm sweeps remain available. Slow holds each arm position for three seconds.

The Mac steps strength curves over Bluetooth and renews short motor leases. Use this adapter's `stop` command to cancel the active playback producer as well as the motor outputs. A shared local playback lock prevents competing loop producers. Power-off/disconnection aborts playback; it is not automatically replayed on reconnect. Loop samples are bounded by the remaining run time, and cleanup sends stop. The independent firmware timeouts also expire outputs if the host disappears. A raw firmware stop command does not itself terminate an unrelated host producer: use the adapter's Stop action when a host loop is running.

Chest/back each address two discs together; they cannot be separated in software. At most four discs are active at once. MOSFET pulses expire within 3000 ms and DRV realtime samples within 2000 ms. The present current limits remain unchanged. The LiPo must be connected and switched on for full-strength operation on the BAT motor rail.

## Wiring and map

- Bus 0: default Feather Wire SDA22/SCL20; PCA9685 0x40 and chest DRV2605L 0x5A.
- Bus 1: Wire1 SDA14/SCL32; back DRV2605L 0x5A.
- PCA VCC: Feather 3V logic. PCA V+: Feather BAT motor rail. Common grounds.
- Both DRV VINs: Feather 3V. Each drives two ERM discs in parallel.

| Zone | Right PCA channel | Left PCA channel |
| --- | --- | --- |
| Waist | 0 | 15 |
| Small of back | 1 | 14 |
| Collarbone | 2 | 13 |
| Upper arm | 3 | 12 |
| Elbow | 4 | 11 |
| Wrist | 6 | 10 |

CH5 and CH7–9 are spare. `body_zone_map.json` records the map; `bind`/`unbind` persist aliases on the Feather. The right wrist was physically identified on CH6 after an initial CH5 assumption was disproved.

## Context and integration

`shirt_prompt.py` describes the independent zones, two pairs, directional sweeps, usual strength curves, authored signals, and three-minute loop option. `shirt_ble.py context` generates it only after a fresh authenticated controller response. An absent/off/unreachable shirt contributes no capability block; old successful presence is not reused. When USB is connected it also powers the Feather, so an inline battery-switch-only off test requires USB unplugged.

The existing build has passed battery-only chest-wave playback and a physical on/off/on context test, including reconnection without re-pairing. The four authored signal timings are initial settings. This branch supplies the local adapter; production wiring into the existing somatic authority, stop ownership, result reporting, and context dispatcher remains pending. Deploys continue through the repository's normal review and Gloria-controlled route.

## Offline tests

```sh
.blevenv/bin/python -m unittest test_shirt_signals test_shirt_loops -v
```

Tests use temporary playback state and fake clocks/transports. They verify the 180-second boundary, last-sample leases, cancellation without restart, disconnect behavior, producer ownership, spatial routes, disc ceiling, and live-only prompt. No test actuates hardware. `broker/tests/test_haptic_shirt_loops.py` runs these checks through the repository's isolated runner without requiring a Bluetooth installation.
