#pragma once
#include "mic_statistics.h"
#include "esp_adc/adc_continuous.h"
#include "esp_timer.h"
#include "driver/gpio.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esphome/core/log.h"

namespace house_mic {
static adc_continuous_handle_t handle = nullptr;
static portMUX_TYPE lock = portMUX_INITIALIZER_UNLOCKED;
static Reading latest;
static int64_t latest_at = 0;
static float pressure_latest = NAN;
static int64_t pressure_at = 0;

static void worker(void *) {
  uint8_t buffer[1024];
  Accumulator accumulated;
  FastPeakMeter fast;
  int64_t started = esp_timer_get_time();
  int64_t pressure_started = started;
  uint32_t pressure_sum = 0, pressure_count = 0;
  for (;;) {
    uint32_t bytes = 0;
    esp_err_t error = adc_continuous_read(handle, buffer, sizeof(buffer), &bytes, 100);
    if (error == ESP_ERR_TIMEOUT) continue;
    if (error != ESP_OK) {
      ESP_LOGE("house_mic", "ADC read failed: %s", esp_err_to_name(error));
      vTaskDelay(pdMS_TO_TICKS(100));
      continue;
    }
    for (uint32_t i = 0; i + SOC_ADC_DIGI_RESULT_BYTES <= bytes; i += SOC_ADC_DIGI_RESULT_BYTES) {
      const auto *sample = reinterpret_cast<const adc_digi_output_data_t *>(buffer + i);
      if (sample->type1.channel == ADC_CHANNEL_6) {
        accumulated.add(sample->type1.data);
        fast.add(sample->type1.data);
      } else if (sample->type1.channel == ADC_CHANNEL_4) {
        pressure_sum += sample->type1.data;
        ++pressure_count;
      }
    }
    int64_t now = esp_timer_get_time();
    if (now - pressure_started >= 250000 && pressure_count) {
      portENTER_CRITICAL(&lock);
      pressure_latest = pressure_sum * 100.0f / (4095.0f * pressure_count);
      pressure_at = now;
      portEXIT_CRITICAL(&lock);
      pressure_sum = pressure_count = 0;
      pressure_started = now;
    }
    if (now - started >= 1000000) {
      Reading reading = accumulated.result();
      reading.level = fast.take_peak();
      portENTER_CRITICAL(&lock);
      latest = reading; latest_at = now;
      portEXIT_CRITICAL(&lock);
      ESP_LOGD("house_mic", "n=%u min=%u max=%u mean=%.1f rms_raw=%.1f fast_level=%.2f high=%.1f",
               reading.count, reading.minimum, reading.maximum, reading.mean, reading.rms,
               reading.level, reading.clipped_high);
      accumulated = Accumulator();
      started = now;
    }
  }
}

inline bool begin() {
  if (handle) return true;
  adc_continuous_handle_cfg_t allocation = {};
  allocation.max_store_buf_size = 4096;
  allocation.conv_frame_size = 512;
  allocation.flags.flush_pool = true;
  esp_err_t error = adc_continuous_new_handle(&allocation, &handle);
  if (error == ESP_OK) {
    adc_digi_pattern_config_t pattern[2] = {};
    pattern[0].atten = ADC_ATTEN_DB_12;
    pattern[0].channel = ADC_CHANNEL_6;  // GPIO34, the supplied microphone wiring.
    pattern[0].unit = ADC_UNIT_1;
    pattern[0].bit_width = SOC_ADC_DIGI_MAX_BITWIDTH;
    pattern[1] = pattern[0];
    pattern[1].channel = ADC_CHANNEL_4;  // GPIO32 pressure, same ADC unit as the mic.
    adc_continuous_config_t config = {};
    config.pattern_num = 2;
    config.adc_pattern = pattern;
    config.sample_freq_hz = 40000;  // Two channels: preserve the mic's 20 ksample/s rate.
    config.conv_mode = ADC_CONV_SINGLE_UNIT_1;
    config.format = ADC_DIGI_OUTPUT_FORMAT_TYPE1;
    error = adc_continuous_config(handle, &config);
  }
  if (error == ESP_OK) error = adc_continuous_start(handle);
  if (error == ESP_OK) {
    gpio_input_enable(GPIO_NUM_32);
    gpio_pullup_dis(GPIO_NUM_32);
    gpio_pulldown_en(GPIO_NUM_32);
    if (xTaskCreatePinnedToCore(worker, "mic_level", 4096, nullptr, 2, nullptr, 1) == pdPASS) return true;
    error = ESP_ERR_NO_MEM;
  }
  ESP_LOGE("house_mic", "Continuous microphone ADC could not start: %s", esp_err_to_name(error));
  if (handle) {
    adc_continuous_stop(handle);
    adc_continuous_deinit(handle);
    handle = nullptr;
  }
  return false;
}

inline float pressure_level() {
  portENTER_CRITICAL(&lock);
  float result = pressure_latest;
  int64_t timestamp = pressure_at;
  portEXIT_CRITICAL(&lock);
  return timestamp && esp_timer_get_time() - timestamp <= 2000000 ? result : NAN;
}

inline float level() {
  portENTER_CRITICAL(&lock);
  Reading result = latest;
  int64_t timestamp = latest_at;
  portEXIT_CRITICAL(&lock);
  if (!result.count || esp_timer_get_time() - timestamp > 3000000) return NAN;
  return result.level;
}
}  // namespace house_mic
