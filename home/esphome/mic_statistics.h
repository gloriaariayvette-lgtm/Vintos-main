#pragma once
#include <cmath>
#include <cstdint>

namespace house_mic {
struct Reading {
  uint32_t count = 0;
  uint16_t minimum = 4095, maximum = 0;
  double mean = 0, rms = 0;
  float level = 0, clipped_high = 0;
};

// DC-independent amplitude; constant bias alone must never count as loud sound.
struct Accumulator {
  uint32_t count = 0, high = 0;
  uint64_t sum = 0, squares = 0;
  uint16_t minimum = 4095, maximum = 0;
  void add(uint16_t sample) {
    count++;
    sum += sample;
    squares += uint64_t(sample) * sample;
    if (sample < minimum) minimum = sample;
    if (sample > maximum) maximum = sample;
    if (sample >= 4090) high++;
  }
  Reading result() const {
    Reading r;
    if (!count) return r;
    r.count = count; r.minimum = minimum; r.maximum = maximum;
    r.mean = double(sum) / count;
    double variance = double(squares) / count - r.mean * r.mean;
    r.rms = std::sqrt(variance > 0 ? variance : 0);
    r.level = float(r.rms * 100.0 / 2047.5);
    if (r.level > 100) r.level = 100;
    r.clipped_high = float(high) * 100.0f / count;
    return r;
  }
};

// Preserve short sounds in a one-second report without treating an isolated
// ADC glitch as a sound. The three-sample median costs 50 us of signal delay.
struct FastPeakMeter {
  Accumulator window;
  uint16_t previous = 0, older = 0;
  bool initialized = false;
  float peak = 0;
  void add(uint16_t value) {
    if (!initialized) { previous = older = value; initialized = true; }
    uint16_t a = older, b = previous, c = value;
    uint16_t middle = a > b ? (b > c ? b : (a > c ? c : a))
                            : (a > c ? a : (b > c ? c : b));
    older = previous; previous = value;
    window.add(middle);
    if (window.count >= 2500) {  // 125 ms at 20 ksample/s.
      float level = window.result().level;
      if (level > peak) peak = level;
      window = Accumulator();
    }
  }
  float take_peak() { float value = peak; peak = 0; return value; }
};
}  // namespace house_mic
