"""Enable ESPHome's reference-counted radio leases for the custom DAC player."""
from esphome.components import wifi
import esphome.config_validation as cv

DEPENDENCIES = ["wifi"]
CONFIG_SCHEMA = cv.Schema({})

async def to_code(config):
    wifi.enable_runtime_power_save_control()
    wifi.enable_runtime_roaming_suppression()
