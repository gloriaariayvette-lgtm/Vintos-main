"""The four shirt signals from Eve's picture. Timings are initial, uncalibrated values.

The meanings belong to the supplied message. These patterns produce vibration;
they do not generate heat or controlled pressure.
"""
import math

MEANINGS = {
    "wrist_to_collarbone": "I’m here. I want you near.",
    "three_taps": "I see you. I’m not going anywhere.",
    "back_sweep": "I’m glad you’re in the room.",
    "long_crest": "I miss you, and I’m staying anyway.",
}


def plan(name, channels, side="right", pair="chest", peak=10):
    """Return (time_seconds, command) events and the time all outputs expire.

    Peak uses the somatic 0–20 scale. Four-disc budget is respected even for
    bilateral wrist-to-collarbone playback. All firmware leases <= 2000 ms.
    """
    if name not in MEANINGS or side not in ("right", "left", "both"):
        raise ValueError("unknown signal or side")
    if pair not in ("chest", "back") or not 0 <= peak <= 20:
        raise ValueError("pair must be chest/back; peak 0..20")
    events = []

    def motor(t, zone, fraction, ms):
        if zone not in channels:
            raise ValueError("unmapped zone: " + zone)
        duty = round(4095 * peak/20 * fraction)
        events.append((t, f"pulse {channels[zone]} {duty} {ms}"))

    def level(t, target, fraction, ms):
        amplitude = round(127 * peak/20 * fraction)
        events.append((t, f"level {target} {amplitude} {ms}"))

    if name == "wrist_to_collarbone":
        sides = ("right", "left") if side == "both" else (side,)
        for i, (place, strength) in enumerate(zip(
                ("wrist", "elbow", "upper_arm", "collarbone"), (.35, .5, .75, 1))):
            for s in sides:
                motor(i*.6, f"{s}_{place}", strength, 800)
        end = 2.6
    elif name == "three_taps":
        for i in range(3):
            level(i*.85, pair, 1, 150)
        end = 1.85
    elif name == "back_sweep":
        motor(0, "left_small_of_back", .5, 900)
        level(.7, "back", .5, 900)
        motor(1.4, "right_small_of_back", .5, 900)
        end = 2.3
    else:
        # One 1.2s rise, 0.6s crest, and 2.4s fade, with 100ms samples.
        for i in range(43):
            t = i/10
            if t < 1.2:
                strength = .5-.5*math.cos(math.pi*t/1.2)
            elif t <= 1.8:
                strength = 1
            else:
                strength = max(0, (4.2-t)/2.4)**1.5
            level(t, pair, strength, 250)
        end = 4.45
    return sorted(events, key=lambda event: event[0]), end
