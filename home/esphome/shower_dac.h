// shower_dac.h - his voice and his songs on the shower board's own amp, as it is wired (GPIO25, the ESP32's DAC).
// ESPHome no longer drives the ESP32's built-in DAC for audio, so this plays a WAV from a URL straight to it with
// ESP-IDF's DAC driver. The WAV is what house_boards.py makes: 16 kHz, mono, 16-bit.
#pragma once
#include <string>
#include <cstring>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/dac_continuous.h"
#include "esp_http_client.h"

namespace shower_dac {

static volatile bool g_stop = false;
static volatile bool g_busy = false;
static TaskHandle_t g_task = nullptr;
static std::string g_url;

static void play_task(void *) {
  g_busy = true;
  dac_continuous_handle_t dac = nullptr;
  dac_continuous_config_t cfg = {};
  cfg.chan_mask = DAC_CHANNEL_MASK_CH0;   // GPIO25
  cfg.desc_num = 4;
  cfg.buf_size = 1024;
  cfg.freq_hz = 16000;
  cfg.offset = 0;
  cfg.clk_src = DAC_DIGI_CLK_SRC_DEFAULT;
  cfg.chan_mode = DAC_CHANNEL_MODE_SIMUL;

  esp_http_client_config_t hc = {};
  hc.url = g_url.c_str();
  hc.timeout_ms = 10000;
  esp_http_client_handle_t client = esp_http_client_init(&hc);
  if (client && esp_http_client_open(client, 0) == ESP_OK && esp_http_client_fetch_headers(client) >= 0 &&
      dac_continuous_new_channels(&cfg, &dac) == ESP_OK && dac_continuous_enable(dac) == ESP_OK) {
    static int16_t in[512];
    static uint8_t out[512];
    // the 44-byte WAV header
    int skip = 44;
    while (skip > 0 && !g_stop) {
      int n = esp_http_client_read(client, (char *) in, skip > (int) sizeof(in) ? sizeof(in) : skip);
      if (n <= 0) break;
      skip -= n;
    }
    int carry = 0;   // a byte left over when a read ends mid-sample
    while (!g_stop) {
      int n = esp_http_client_read(client, ((char *) in) + carry, sizeof(in) - carry);
      if (n <= 0) break;
      n += carry;
      int samples = n / 2;
      for (int i = 0; i < samples; i++) out[i] = (uint8_t) ((in[i] >> 8) + 128);
      carry = n % 2;
      if (carry) ((char *) in)[0] = ((char *) in)[n - 1];
      size_t written = 0;
      dac_continuous_write(dac, out, samples, &written, -1);
    }
    dac_continuous_disable(dac);
  }
  if (dac) dac_continuous_del_channels(dac);
  if (client) { esp_http_client_close(client); esp_http_client_cleanup(client); }
  g_busy = false;
  g_task = nullptr;
  vTaskDelete(nullptr);
}

inline void stop() {
  g_stop = true;
  for (int i = 0; i < 100 && g_task != nullptr; i++) vTaskDelay(pdMS_TO_TICKS(20));
}

inline void play(const std::string &url) {
  stop();
  g_url = url;
  g_stop = false;
  xTaskCreatePinnedToCore(play_task, "shower_dac", 6144, nullptr, 5, &g_task, 1);
}

inline bool busy() { return g_busy; }

}  // namespace shower_dac
