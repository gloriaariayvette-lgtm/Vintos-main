// Buffered 16 kHz mono PCM WAV player for the existing GPIO25 DAC/amp.
#pragma once
#include <atomic>
#include <new>
#include <string>
#include "wav_pcm.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/stream_buffer.h"
#include "driver/dac_continuous.h"
#include "driver/gpio.h"
#include "esp_http_client.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "esp_system.h"
#include "esp_heap_caps.h"
#include "esphome/components/wifi/wifi_component.h"
#include "esphome/core/log.h"

namespace shower_dac {
static std::atomic<bool> g_stop{false}, g_busy{false};
static std::atomic<int> g_status{0};
// Sole playback-task ownership; idle is a grounded amplifier input, not a running DAC.
static dac_continuous_handle_t g_dac=nullptr;
static std::atomic<bool> g_idle_muted{false};
inline bool mute_idle() {
  esp_err_t level = gpio_set_level(GPIO_NUM_25, 0);
  esp_err_t mode = gpio_set_direction(GPIO_NUM_25, GPIO_MODE_INPUT_OUTPUT);
  bool ok = level == ESP_OK && mode == ESP_OK && gpio_get_level(GPIO_NUM_25) == 0;
  g_idle_muted.store(ok);
  if(!ok)ESP_LOGE("shower_dac", "Failed to ground idle amplifier input");
  return ok;
}
inline bool idle_muted(){return g_idle_muted.load();}
struct Request { std::string url; float volume; };
struct Stream {
  esp_http_client_handle_t client=nullptr;
  StreamBufferHandle_t buffer=nullptr;
  std::atomic<bool> done{false};
  std::atomic<int> result{0};  // 1 complete, 2 stopped, 3 truncated/transport error
  uint32_t bytes=0;
  float volume=1.0f;
};
// Temporary empty reads/timeouts are not EOF. All waits are bounded and observe stop.
inline int read_http(esp_http_client_handle_t client,uint8_t *out,size_t size) {
  int64_t deadline=esp_timer_get_time()+10000000;
  while(!g_stop.load()) {
    int n=esp_http_client_read(client,reinterpret_cast<char *>(out),size);
    if(n>0)return n;
    if(n<0 && n!=-ESP_ERR_HTTP_EAGAIN)return -1;
    if(esp_http_client_is_complete_data_received(client))return 0;
    if(esp_timer_get_time()>=deadline)return -1;
    vTaskDelay(pdMS_TO_TICKS(10));
  }
  return -1;
}
static void fetch_task(void *arg) {
  auto *s=static_cast<Stream *>(arg);
  uint8_t in[2048],out[2048];
  shower_pcm::Upsampler upsample;
  uint32_t remaining=s->bytes,index=0;
  size_t carry=0;
  int result=1;
  while(remaining && !g_stop.load()) {
    int n=read_http(s->client,in+carry,std::min<size_t>(sizeof(in)-carry,remaining));
    if(n<=0){result=3;break;}
    remaining-=n;
    size_t count=n+carry,samples=count/2;
    for(size_t i=0;i<samples;++i) {
      int32_t sample=shower_pcm::le16(in+2*i);
      if(sample>=32768)sample-=65536;
      upsample.sample(int16_t(sample),index++,s->bytes/2,s->volume,out+2*i);
    }
    carry=count&1;
    if(carry)in[0]=in[count-1];
    size_t sent=0;
    while(sent<samples*2 && !g_stop.load())
      sent+=xStreamBufferSend(s->buffer,out+sent,samples*2-sent,pdMS_TO_TICKS(50));
  }
  if(g_stop.load())result=2;
  s->result.store(result);
  s->done.store(true);
  vTaskDelete(nullptr);
}
static void play_task(void *arg) {
  auto *req=static_cast<Request *>(arg);
  Stream s;
  dac_continuous_handle_t dac=nullptr;
  bool enabled=false,producer=false;
  auto *out=new(std::nothrow) uint8_t[4096];
  uint32_t frames=0;
  uint8_t last=128;
  int result=5;
  auto *wifi=esphome::wifi::global_wifi_component;
  bool network_lease=wifi && wifi->request_high_performance();
  if(wifi)wifi->request_roaming_suppression();
  do {
    if(!out)break;
    esp_http_client_config_t hc={};hc.url=req->url.c_str();hc.timeout_ms=1000;
    s.client=esp_http_client_init(&hc);
    if(!s.client || esp_http_client_open(s.client,0)!=ESP_OK || esp_http_client_fetch_headers(s.client)<0)break;
    int status=esp_http_client_get_status_code(s.client);
    if(status!=200){ESP_LOGW("shower_dac","HTTP status %d",status);break;}
    auto read=[&](uint8_t *b,size_t n){return read_http(s.client,b,n);};
    if(!shower_pcm::header(read,s.bytes)){ESP_LOGW("shower_dac","Invalid/truncated WAV; require PCM16 mono 16000 Hz");break;}
    s.volume=req->volume;
    s.buffer=xStreamBufferCreate(12288,1);
    if(!s.buffer)break;
    if(xTaskCreatePinnedToCore(fetch_task,"shower_fetch",8192,&s,3,nullptr,1)!=pdPASS)break;
    producer=true;
    while(!g_stop.load() && !s.done.load() && xStreamBufferBytesAvailable(s.buffer)<8192)
      vTaskDelay(pdMS_TO_TICKS(10));
    if(g_stop.load()){result=4;break;}
    if(s.result.load()==3){ESP_LOGW("shower_dac","Audio truncated during prebuffer");break;}
    wifi_ps_type_t radio_mode=WIFI_PS_MIN_MODEM;
    esp_wifi_get_ps(&radio_mode);
    ESP_LOGI("shower_dac","Audio renderer=2 radio lease=%d mode=%d heap=%u largest=%u",
             int(network_lease),int(radio_mode),unsigned(esp_get_free_heap_size()),
             unsigned(heap_caps_get_largest_free_block(MALLOC_CAP_8BIT)));
    dac_continuous_config_t cfg={};
    cfg.chan_mask=DAC_CHANNEL_MASK_CH0;cfg.desc_num=4;cfg.buf_size=2048;
    cfg.freq_hz=32000;cfg.clk_src=DAC_DIGI_CLK_SRC_DEFAULT;cfg.chan_mode=DAC_CHANNEL_MODE_SIMUL;
    if(!g_dac) {
      g_idle_muted.store(false);
      gpio_reset_pin(GPIO_NUM_25);
      if(dac_continuous_new_channels(&cfg,&dac)!=ESP_OK)break;
      if(dac_continuous_enable(dac)!=ESP_OK) {
        dac_continuous_del_channels(dac);dac=nullptr;break;
      }
      enabled=true;
      g_dac=dac;
      // First use: slew DC from zero to midpoint over 128 ms, rather than a hard step.
      shower_pcm::transition(out,4096,0,128);
      size_t primed=0;
      if(dac_continuous_write(dac,out,4096,&primed,500)!=ESP_OK || primed!=4096)break;
    }
    dac=g_dac;enabled=true;g_status.store(2);
    bool recovering=false;result=2;
    while(!g_stop.load()) {
      size_t n=0;
      int64_t deadline=esp_timer_get_time()+100000;
      while(n<4096 && !g_stop.load()) {
        n+=xStreamBufferReceive(s.buffer,out+n,4096-n,pdMS_TO_TICKS(10));
        if(s.done.load() && !xStreamBufferBytesAvailable(s.buffer))break;
        if(esp_timer_get_time()>=deadline)break;
      }
      if(g_stop.load())break;
      bool exhausted=s.done.load() && !xStreamBufferBytesAvailable(s.buffer);
      if(n) {
        if(recovering) {
          // Smooth recovery from midpoint silence; retain the actual received music samples.
          size_t fade=std::min<size_t>(n,640);
          for(size_t i=0;i<fade;++i)out[i]=uint8_t(128+(int(out[i])-128)*int(i+1)/int(fade));
          recovering=false;
        }
        size_t written=0;
        if(dac_continuous_write(dac,out,n,&written,500)!=ESP_OK || written!=n){result=5;break;}
        frames+=written;last=out[n-1];
      }
      if(exhausted){result=s.result.load()==1?3:5;break;}
      if(n<4096) {
        // Network stalls become bounded, faded silence, never a stopped/restarted DMA clock.
        shower_pcm::transition(out,640,last,128);
        memset(out+640,128,4096-640);
        size_t written=0;
        if(dac_continuous_write(dac,out,4096,&written,500)!=ESP_OK || written!=4096){result=5;break;}
        last=128;recovering=true;
        ESP_LOGW("shower_dac","Audio network starvation: inserted midpoint silence");
      }
    }
    if(g_stop.load())result=4;
    // Fade all the way to ground before disabling the DAC, avoiding an abrupt DC step.
    shower_pcm::transition(out,4096,last,0);
    size_t written=0;
    if(dac_continuous_write(dac,out,4096,&written,500)!=ESP_OK || written!=4096)result=5;
    vTaskDelay(pdMS_TO_TICKS(300));
  } while(false);
  g_stop.store(true);
  if(producer)while(!s.done.load())vTaskDelay(pdMS_TO_TICKS(10));
  // No active DAC/DMA clock or floating signal lead between clips.
  if(dac && enabled) {
    if(dac_continuous_disable(dac)!=ESP_OK) {
      ESP_LOGE("shower_dac", "DAC disable failed");result=5;
    } else if(dac_continuous_del_channels(dac)!=ESP_OK) {
      ESP_LOGE("shower_dac", "DAC release failed");result=5;
    } else {
      g_dac=nullptr;dac=nullptr;
    }
  }
  if(!g_dac && !mute_idle())result=5;
  ESP_LOGI("shower_dac", "Idle output muted=%d pin=%d", int(g_idle_muted.load()), gpio_get_level(GPIO_NUM_25));
  if(s.buffer)vStreamBufferDelete(s.buffer);
  if(s.client){esp_http_client_close(s.client);esp_http_client_cleanup(s.client);}
  delete[] out;delete req;
  if(wifi) {
    wifi->release_roaming_suppression();
    if(network_lease)wifi->release_high_performance();
  }
  ESP_LOGI("shower_dac","Playback result=%d frames=%u expected=%u",result,unsigned(frames),unsigned(s.bytes));
  g_status.store(result);g_busy.store(false);
  vTaskDelete(nullptr);
}
inline void stop() {
  g_stop.store(true);
  for(int i=0;i<100 && g_busy.load();++i)vTaskDelay(pdMS_TO_TICKS(20));
}
inline void play(const std::string &url,float volume=1.0f) {
  stop();
  if(g_busy.load()){ESP_LOGW("shower_dac","Previous playback is still stopping");return;}
  auto *req=new(std::nothrow) Request{url,volume};
  if(!req){g_status.store(5);return;}
  g_stop.store(false);g_busy.store(true);g_status.store(1);
  if(xTaskCreatePinnedToCore(play_task,"shower_dac",8192,req,5,nullptr,1)!=pdPASS) {
    delete req;g_busy.store(false);g_status.store(5);
  }
}
inline bool busy(){return g_busy.load();}
inline const char *status(){
  switch(g_status.load()) {
    case 1:return "buffering";case 2:return "playing";case 3:return "finished";
    case 4:return "stopped";case 5:return "error";default:return "idle";
  }
}
}  // namespace shower_dac
