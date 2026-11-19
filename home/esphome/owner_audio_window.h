#pragma once
#include <cstdint>

namespace house_steam {
// Only the encrypted owner API arms this volatile window; MQTT cannot arm it.
class OwnerAudioWindow {
 public:
  void arm(uint32_t now) { started_ = now; armed_ = true; }
  bool active(uint32_t now) const {
    return armed_ && uint32_t(now - started_) < 90000u;
  }
  void expire(uint32_t now) { if (armed_ && !active(now)) armed_ = false; }
  bool allows(bool qualified_steam, bool phone_near, uint32_t now) const {
    return phone_near && (qualified_steam || active(now));
  }
 private:
  uint32_t started_ = 0;
  bool armed_ = false;
};
}  // namespace house_steam
