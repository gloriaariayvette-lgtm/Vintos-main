#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>
#include <Adafruit_DRV2605.h>
#include <Preferences.h>

// Final wiring: bus 0 SDA22/SCL20; bus 1 SDA14/SCL32.
// Independent timers; at most four discs active with the present power wiring.
class HapticApi {
 public:
  Adafruit_PWMServoDriver pwm{0x40};
  Adafruit_DRV2605 chest, back;
  bool pcaOK = false, chestOK = false, backOK = false;
  String zones[16];
  String active = "none";

  void begin() {
    Wire.begin();
    Wire1.begin(14, 32);
    Wire.setTimeOut(50);
    Wire1.setTimeOut(50);
    rawWrite(Wire, 0x40, 0xFD, 0x10);
    rawWrite(Wire, 0x5A, 0x0C, 0);
    rawWrite(Wire1, 0x5A, 0x0C, 0);
    pcaOK = pwm.begin();
    if (pcaOK) {
      rawWrite(Wire, 0x40, 0xFD, 0x10);
      pwm.setPWMFreq(500);
    }
    chestOK = chest.begin(&Wire);
    backOK = back.begin(&Wire1);
    if (chestOK) configure(chest);
    if (backOK) configure(back);
    stop();
    prefsOK = prefs.begin("haptic-shirt", false);
    if (prefsOK) {
      for (unsigned ch = 0; ch < 16; ++ch) {
        char key[8];
        snprintf(key, sizeof(key), "zone%u", ch);
        zones[ch] = prefs.getString(key, "");
      }
    }
  }

  void stop() {
    if (pcaOK) rawWrite(Wire, 0x40, 0xFD, 0x10);
    if (chestOK) silence(chest);
    if (backOK) silence(back);
    for (unsigned i = 0; i < 16; ++i) chArmed[i] = false;
    pairArmed[0] = pairArmed[1] = false;
    active = "none";
  }

  bool pulse(unsigned ch, unsigned duty, unsigned ms) {
    if (!pcaOK || ch >= 16 || duty > 4095 || ms == 0 || ms > 3000) return false;
    if (duty && !chArmed[ch] && discCount() >= 4) return false;
    uint16_t on = duty == 4095 ? 4096 : 0;
    uint16_t off = duty == 0 ? 4096 : (duty == 4095 ? 0 : duty);
    if (pwm.setPWM(ch, on, off) != 0) return false;
    chUntil[ch] = millis() + ms;
    chArmed[ch] = duty != 0;
    refreshActive();
    Serial.printf("t=%lu CH%02u duty=%u duration=%ums discs=%u\n", (unsigned long)millis(), ch, duty, ms, discCount());
    return true;
  }

  bool effect(const String &pair, unsigned id = 47) {
    if (id < 1 || id > 123) return false;
    Adafruit_DRV2605 *d = nullptr;
    if (pair == "chest" && chestOK) d = &chest;
    if ((pair == "back" || pair == "shoulder_blades") && backOK) d = &back;
    if (!d) return false;
    unsigned index = d == &chest ? 0 : 1;
    if (!pairArmed[index] && discCount() + 2 > 4) return false;
    silence(*d);
    d->setMode(DRV2605_MODE_INTTRIG);
    d->setWaveform(0, id);
    d->setWaveform(1, 0);
    d->go();
    pairUntil[index] = millis() + 2000;
    pairArmed[index] = true;
    refreshActive();
    Serial.printf("PAIR %s effect=%u\n", pair.c_str(), id);
    return true;
  }

  bool level(const String &pair, unsigned amplitude, unsigned ms) {
    if (amplitude > 127 || ms == 0 || ms > 2000) return false;
    Adafruit_DRV2605 *d = nullptr;
    if (pair == "chest" && chestOK) d = &chest;
    if ((pair == "back" || pair == "shoulder_blades") && backOK) d = &back;
    if (!d) return false;
    unsigned index = d == &chest ? 0 : 1;
    if (amplitude && !pairArmed[index] && discCount() + 2 > 4) return false;
    if (amplitude) {
      d->stop();
      d->setMode(DRV2605_MODE_REALTIME);
      d->setRealtimeValue(amplitude);
    } else silence(*d);
    pairArmed[index] = amplitude != 0;
    pairUntil[index] = millis() + ms;
    refreshActive();
    Serial.printf("LEVEL %s amplitude=%u duration=%ums\n", pair.c_str(), amplitude, ms);
    return true;
  }

  bool zone(const String &name) {
    if (name == "chest" || name == "back" || name == "shoulder_blades") return effect(name);
    for (unsigned ch = 0; ch < 16; ++ch) {
      if (zones[ch].length() && zones[ch] == name) return pulse(ch, 4095, 1000);
    }
    return false;
  }

  int channel(const String &name) {
    for (unsigned ch = 0; ch < 16; ++ch) if (zones[ch].length() && zones[ch] == name) return ch;
    return -1;
  }

  unsigned discCount() {
    unsigned count = 2 * unsigned(pairArmed[0]) + 2 * unsigned(pairArmed[1]);
    for (bool on : chArmed) count += on;
    return count;
  }

  bool bind(const String &name, unsigned ch) {
    if (!prefsOK || ch >= 16 || name.length() == 0 || name.length() > 23) return false;
    if (name == "chest" || name == "back" || name == "shoulder_blades") return false;
    for (unsigned i = 0; i < name.length(); ++i) {
      char c = name[i];
      if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '_')) return false;
    }
    for (unsigned i = 0; i < 16; ++i) if (i != ch && zones[i] == name) return false;
    stop();
    char key[8];
    snprintf(key, sizeof(key), "zone%u", ch);
    if (!prefs.putString(key, name)) return false;
    zones[ch] = name;
    Serial.printf("BOUND %s -> CH%02u\n", name.c_str(), ch);
    return true;
  }

  bool unbind(unsigned ch) {
    if (!prefsOK || ch >= 16) return false;
    stop();
    char key[8]; snprintf(key, sizeof(key), "zone%u", ch);
    if (zones[ch].length() && !prefs.remove(key)) return false;
    zones[ch] = "";
    Serial.printf("UNBOUND CH%02u\n", ch);
    return true;
  }

  void update() {
    bool changed = false;
    for (unsigned ch = 0; ch < 16; ++ch) {
      if (chArmed[ch] && int32_t(millis() - chUntil[ch]) >= 0) {
        pwm.setPWM(ch, 0, 4096); chArmed[ch] = false; changed = true;
        Serial.printf("t=%lu CH%02u off\n", (unsigned long)millis(), ch);
      }
    }
    if (pairArmed[0] && int32_t(millis() - pairUntil[0]) >= 0) { silence(chest); pairArmed[0] = false; changed = true; }
    if (pairArmed[1] && int32_t(millis() - pairUntil[1]) >= 0) { silence(back); pairArmed[1] = false; changed = true; }
    if (changed) refreshActive();
  }

  void map() {
    Serial.println("chest -> DRV bus0 0x5A (pair)");
    Serial.println("back / shoulder_blades -> DRV bus1 0x5A (pair)");
    for (unsigned ch = 0; ch < 16; ++ch) {
      Serial.printf("CH%02u -> %s\n", ch, zones[ch].length() ? zones[ch].c_str() : "unassigned");
    }
  }

  void status() {
    Serial.printf("PCA9685=%s chest=%s back=%s active=%s\n", pcaOK ? "found" : "missing",
                  chestOK ? "found" : "missing", backOK ? "found" : "missing", active.c_str());
    Serial.printf("active_discs=%u limit=4\n", discCount());
    if (pcaOK) {
      Serial.print("PCA ON registers:");
      for (unsigned ch = 0; ch < 16; ++ch) Serial.printf(" %u:%u", ch, pwm.getPWM(ch, false));
      Serial.println();
      Serial.print("PCA OFF registers:");
      for (unsigned ch = 0; ch < 16; ++ch) Serial.printf(" %u:%u", ch, pwm.getPWM(ch, true));
      Serial.println();
    }
    if (chestOK) Serial.printf("chest status=0x%02X go=%u\n", chest.readRegister8(DRV2605_REG_STATUS), chest.readRegister8(DRV2605_REG_GO));
    if (backOK) Serial.printf("back status=0x%02X go=%u\n", back.readRegister8(DRV2605_REG_STATUS), back.readRegister8(DRV2605_REG_GO));
  }

  void voltage() {
    // Feather V2 GPIO35 reads BAT through the onboard 200K/200K divider.
    uint32_t total = 0;
    for (unsigned i = 0; i < 16; ++i) total += analogReadMilliVolts(35);
    Serial.printf("BAT rail estimate: %lumV active=%s\n", (unsigned long)(total / 8), active.c_str());
  }

 private:
  static void silence(Adafruit_DRV2605 &d) {
    d.setRealtimeValue(0);
    d.stop();
    d.setMode(DRV2605_MODE_INTTRIG);
  }
  Preferences prefs;
  bool prefsOK = false;
  bool chArmed[16] = {}, pairArmed[2] = {};
  uint32_t chUntil[16] = {}, pairUntil[2] = {};
  void refreshActive() {
    active = "";
    for (unsigned ch = 0; ch < 16; ++ch) if (chArmed[ch]) { if (active.length()) active += ","; active += "CH" + String(ch); }
    if (pairArmed[0]) { if (active.length()) active += ","; active += "chest"; }
    if (pairArmed[1]) { if (active.length()) active += ","; active += "back"; }
    if (!active.length()) active = "none";
  }
  static void configure(Adafruit_DRV2605 &d) {
    d.useERM();
    d.selectLibrary(1);
    d.setMode(DRV2605_MODE_INTTRIG);
  }
  static void rawWrite(TwoWire &w, uint8_t address, uint8_t reg, uint8_t value) {
    w.beginTransmission(address);
    w.write(reg);
    w.write(value);
    w.endTransmission();
  }
};

HapticApi haptics;
bool cycling = false;
unsigned cycleChannel = 0;
uint32_t nextCycleAt = 0;
bool sweeping = false;
unsigned sweepIndex = 0, sweepSides = 1, sweepStepMs = 160;
bool sweepHold = false;
String selectedPace = "normal";
int sweepChannels[2][3];
uint32_t nextSweepAt = 0;

bool startSweep(const String &side, const String &direction, unsigned stepMs, bool arm = false, bool hold = false) {
  if ((side != "right" && side != "left" && side != "both") ||
      ((!arm && direction != "up" && direction != "down") || (arm && direction != "out" && direction != "in")) || stepMs < 100 || (stepMs > 500 && !(hold && stepMs == 3000))) return false;
  sweepSides = side == "both" ? 2 : 1;
  for (unsigned s = 0; s < sweepSides; ++s) {
    String prefix = (side == "both" ? (s == 0 ? "right" : "left") : side) + String("_");
    const char *bodyPlaces[] = {"waist", "collarbone", "upper_arm"};
    const char *armPlaces[] = {"upper_arm", "elbow", "wrist"};
    const char **places = arm ? armPlaces : bodyPlaces;
    for (unsigned i = 0; i < 3; ++i) {
      int ch = haptics.channel(prefix + places[(direction == "up" || direction == "out") ? i : 2-i]);
      if (ch < 0) return false;
      sweepChannels[s][i] = ch;
    }
  }
  haptics.stop(); sweepHold = hold; sweepIndex = 0; sweepStepMs = stepMs; nextSweepAt = millis(); sweeping = true;
  Serial.printf("SWEEP %s %s step=%ums\n", side.c_str(), direction.c_str(), stepMs);
  return true;
}

bool number(const char *s, unsigned max, unsigned &value) {
  if (!s || !*s) return false;
  value = 0;
  for (; *s; ++s) {
    if (*s < '0' || *s > '9') return false;
    unsigned digit = *s - '0';
    if (digit > max || value > (max - digit) / 10) return false;
    value = value * 10 + digit;
  }
  return true;
}

void help() {
  Serial.println("status | voltage | map | stop | cycle");
  Serial.println("pulse <channel 0..15> <duty 0..4095> <ms 1..3000>");
  Serial.println("effect <chest|back> <effect 1..123> | zone <name>");
  Serial.println("level <chest|back> <amplitude 0..127> <ms 1..2000>");
  Serial.println("pace <slow|normal|fast>; slow holds each motor 3000ms");
  Serial.println("arm <right|left|both> <out|in> [slow|normal|fast|step_ms 100..500]");
  Serial.println("bind <body_zone_name> <channel 0..15> | unbind <channel 0..15>");
  Serial.println("together <zone1> <zone2> [zone3] (maximum 4 discs)");
  Serial.println("sweep <right|left|both> <up|down> [step_ms 100..500; default 160]");
  Serial.println("cycle: one full-power 1000ms pulse per channel, 3 seconds between starts; then all off.");
}

void command(char *line) {
  char *context = nullptr;
  char *args[5] = {};
  unsigned count = 0;
  for (char *p = strtok_r(line, " \t\r", &context); p; p = strtok_r(nullptr, " \t\r", &context)) {
    if (count == 5) break;
    args[count++] = p;
  }
  if (!count) return;
  String cmd(args[0]);
  unsigned ch, duty, ms, id;
  bool ok = false;
  if (cmd == "help" && count == 1) { help(); return; }
  if (cmd == "status" && count == 1) { haptics.status(); return; }
  if (cmd == "voltage" && count == 1) { haptics.voltage(); return; }
  if (cmd == "map" && count == 1) { haptics.map(); return; }
  cycling = false;
  sweeping = false;
  if (cmd == "stop" && count == 1) {
    haptics.stop(); Serial.println("all off"); return;
  } else if (cmd == "pace" && count == 2 && (String(args[1]) == "slow" || String(args[1]) == "normal" || String(args[1]) == "fast")) {
    haptics.stop(); selectedPace = args[1]; Serial.printf("PACE %s\n", selectedPace.c_str()); return;
  } else if (cmd == "cycle" && count == 1 && haptics.pcaOK) {
    haptics.stop(); cycling = true; cycleChannel = 0; nextCycleAt = millis();
    Serial.println("CYCLE START: CH00 through CH11"); return;
  } else if (cmd == "pulse" && count == 4 && number(args[1], 15, ch) && number(args[2], 4095, duty) && number(args[3], 3000, ms)) {
    ok = haptics.pulse(ch, duty, ms);
  } else if (cmd == "level" && count == 4 && number(args[2], 127, duty) && number(args[3], 2000, ms)) {
    ok = haptics.level(args[1], duty, ms);
  } else if (cmd == "effect" && count == 3 && number(args[2], 123, id)) {
    ok = haptics.effect(args[1], id);
  } else if (cmd == "zone" && count == 2) {
    ok = haptics.zone(args[1]);
  } else if (cmd == "unbind" && count == 2 && number(args[1], 15, ch)) {
    ok = haptics.unbind(ch);
  } else if (cmd == "bind" && count == 3 && number(args[2], 15, ch)) {
    ok = haptics.bind(args[1], ch);
  } else if (cmd == "together" && (count == 3 || count == 4)) {
    haptics.stop(); ok = true;
    for (unsigned i = 1; i < count && ok; ++i) ok = haptics.zone(args[i]);
  } else if ((cmd == "sweep" || cmd == "arm") && (count == 3 || count == 4)) {
    String pace = count == 4 ? String(args[3]) : selectedPace;
    unsigned stepMs = cmd == "arm" ? 300 : 160;
    bool hold = pace == "slow";
    bool valid = true;
    if (hold) stepMs = 3000;
    else if (pace == "fast") stepMs = 160;
    else if (pace != "normal") valid = number(pace.c_str(), 500, stepMs);
    if (valid) ok = startSweep(args[1], args[2], stepMs, cmd == "arm", hold);
  }
  if (!ok) { haptics.stop(); Serial.println("ERROR: invalid command, missing zone/device, or 4-disc limit; all off"); }
}

void setup() {
  Serial.begin(115200);
  delay(1500);
  haptics.begin();
  Serial.println("ready: all motors off");
  haptics.status();
  help();
}

void loop() {
  static char line[100];
  static unsigned used = 0;
  static bool overflow = false;
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') {
      if (overflow) { cycling = sweeping = false; haptics.stop(); Serial.println("ERROR: command too long; all off"); }
      else { line[used] = 0; command(line); }
      used = 0; overflow = false;
    } else if (used < sizeof(line) - 1) line[used++] = c;
    else overflow = true;
  }
  haptics.update();
  if (sweeping && int32_t(millis() - nextSweepAt) >= 0) {
    unsigned duration = sweepHold ? 3000 : (sweepSides == 2 ? sweepStepMs - 10 : sweepStepMs + 100);
    for (unsigned s = 0; s < sweepSides; ++s) {
      if (!haptics.pulse(sweepChannels[s][sweepIndex], 4095, duration)) {
        sweeping = false; haptics.stop(); Serial.println("SWEEP ERROR: all off"); break;
      }
    }
    if (sweeping && ++sweepIndex == 3) { sweeping = false; Serial.println("SWEEP queued; pulses expire automatically"); }
    nextSweepAt = millis() + sweepStepMs;
  }
  if (cycling && int32_t(millis() - nextCycleAt) >= 0) {
    if (cycleChannel == 12) { cycling = false; haptics.stop(); Serial.println("CYCLE DONE: all off"); }
    else {
      if (!haptics.pulse(cycleChannel++, 4095, 1000)) { cycling = false; haptics.stop(); Serial.println("CYCLE ERROR: all off"); }
      nextCycleAt = millis() + 3000;
    }
  }
  delay(2);
}
