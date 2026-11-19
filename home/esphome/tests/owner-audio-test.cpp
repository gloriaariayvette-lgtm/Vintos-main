#include "owner_audio_window.h"
#include <cassert>
#include <iostream>

int main() {
  house_steam::OwnerAudioWindow window;
  assert(!window.active(0));
  assert(!window.allows(false, true, 100));
  assert(window.allows(true, true, 100));
  assert(!window.allows(true, false, 100));
  window.arm(1000);
  assert(window.allows(false, true, 1000));
  assert(!window.allows(false, false, 1000));
  assert(window.active(90999));
  assert(!window.active(91000));
  assert(!window.allows(false, true, 91000));
  assert(window.allows(true, true, 91000));
  window.expire(91000);
  assert(!window.active(1000));  // expired window cannot return after timer rollover
  window.arm(0xfffff000u);
  assert(window.active(uint32_t(0xfffff000u + 89999u)));
  assert(!window.active(uint32_t(0xfffff000u + 90000u)));
  house_steam::OwnerAudioWindow rebooted;
  assert(!rebooted.allows(false, true, 100));
  std::cout << "PASS: owner-only arm, phone gate, 90s expiry, normal steam, rollover, reboot disarm\n";
}
