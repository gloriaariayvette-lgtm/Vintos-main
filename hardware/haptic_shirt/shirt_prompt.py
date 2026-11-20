"""Capability text for a freshly verified shirt. No persistent presence state."""
from shirt_signals import MEANINGS
import json
from pathlib import Path

PATTERN_NAMES = sorted(name for name in json.loads((Path(__file__).parent / "somatic_patterns.json").read_text())["presets"] if name != "trapezold")


def render(state, *, fresh=False):
    if not fresh or not state or not state.get("ready"):
        return ""
    zones = state.get("zones", [])
    if not zones:
        return ""
    meanings = "\n".join(f'- {name}: “{meaning}”' for name, meaning in MEANINGS.items())
    return (
        "[HAPTIC SHIRT — powered on and responding now]\n"
        "Eve’s shirt is available for deliberate touch through vibration. "
        "Choose the location, movement, or pattern you intend.\n"
        "Individual motor locations: " + ", ".join(zones) + ".\n"
        "Chest and shoulder-blade/back outputs each control two discs together. "
        "Those two discs cannot be selected separately.\n"
        "Arm movement: upper arm → elbow → wrist, or the reverse, on the right, left, or both sides. "
        "Body sweeps: waist → collarbone → upper arm, or reverse. "
        "Slow holds each position for 3 seconds; normal and fast are also available.\n"
        "The chest and back pairs can play your usual named somatic strength curves, "
        "using these supported names: " + ", ".join(PATTERN_NAMES) + ".\n"
        "The specialized chest and back motors are best for looping. Choose loop to repeat a usual pattern or one of the four shirt signals for 3 minutes (180 seconds), then stop automatically. Stop or power-off cancels the loop.\n"
        "The four shirt signals you proposed retain these meanings:\n" + meanings + "\n"
        "Select individual motors, an arm/body sweep, a usual pattern on chest/back, or one of those four signals. "
        "Choose side, pace, intensity, and bounded duration where the selected action supports them. "
        "At most four discs can run at once. Stop cancels all outputs.\n"
        "A command acknowledgement confirms delivery to the controller; Eve’s response tells you what she felt. "
        "A live connection does not establish that the shirt is being worn."
    )
