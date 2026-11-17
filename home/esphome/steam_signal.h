#pragma once
#include <algorithm>
#include <cmath>
#include <cstdint>

namespace house_steam {
// Low-going pad input. Use temporal evidence, never one rail excursion.
class Signal {
 public:
  int update(float volts, float on, uint32_t now) {
    if (!std::isfinite(volts) || volts < 0 || volts > 3.6f ||
        !std::isfinite(on) || on < 3 || on > 100) {
      count_ = pos_ = 0; pending_ = false; score_ = NAN;
      return -1;
    }
    // Bound a single bad conversion's influence on the 30-second window.
    const float wet = std::min(40.0f, std::max(0.0f, (1.0f - volts / 3.3f) * 100.0f));
    values_[pos_] = wet; pos_ = (pos_ + 1) % 15;
    if (count_ < 15) ++count_;
    float sum = 0; unsigned active = 0;
    for (unsigned i = 0; i < count_; ++i) {
      sum += values_[i]; if (values_[i] >= 12.0f) ++active;
    }
    score_ = sum / count_;
    if (count_ < 15) { pending_ = false; return -1; }
    const float off = on - 2.0f;
    const int target = score_ >= on && active >= 3 ? 1 : (score_ <= off ? 0 : -1);
    if (target < 0 || target == state_) { pending_ = false; return state_; }
    if (!pending_ || candidate_ != target) { candidate_ = target; since_ = now; pending_ = true; }
    if (uint32_t(now - since_) >= (target ? 10000u : 60000u)) {
      state_ = target; pending_ = false;
    }
    // A clean initial window is sufficient to establish dry; re-release is debounced.
    if (state_ < 0 && target == 0) { state_ = 0; pending_ = false; }
    return state_;
  }
  float score() const { return score_; }
 private:
  float values_[15] = {}, score_ = NAN;
  unsigned count_ = 0, pos_ = 0;
  int state_ = -1, candidate_ = -1;
  uint32_t since_ = 0;
  bool pending_ = false;
};
}  // namespace house_steam
