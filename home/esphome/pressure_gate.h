#pragma once
#include <cmath>
#include <cstdint>

namespace house_pressure {
// Relative ADC level, not kilograms. Unknown until a stable threshold is crossed.
class Gate {
 public:
  Gate(uint32_t on_ms = 1000, uint32_t off_ms = 1500)
      : on_ms_(on_ms), off_ms_(off_ms) {}
  int update(float level, float on, float off, uint32_t now) {
    if (!std::isfinite(level) || !std::isfinite(on) || !std::isfinite(off) ||
        level < 0 || level > 100 || off < 0 || on > 100 || off >= on) {
      state_ = -1;
      pending_ = false;
      return state_;
    }
    int target = level >= on ? 1 : (level <= off ? 0 : -1);
    if (target < 0 || target == state_) {
      pending_ = false;
      return state_;
    }
    if (!pending_ || target != candidate_) {
      candidate_ = target;
      since_ = now;
      pending_ = true;
    }
    if (uint32_t(now - since_) >= (target ? on_ms_ : off_ms_)) {
      state_ = target;
      pending_ = false;
    }
    return state_;
  }
 private:
  uint32_t on_ms_, off_ms_, since_ = 0;
  int state_ = -1, candidate_ = -1;
  bool pending_ = false;
};
}  // namespace house_pressure
