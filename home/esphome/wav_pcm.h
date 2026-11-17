#pragma once
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
namespace shower_pcm {
inline uint16_t le16(const uint8_t *p) { return uint16_t(p[0]) | uint16_t(p[1]) << 8; }
inline uint32_t le32(const uint8_t *p) { return uint32_t(le16(p)) | uint32_t(le16(p+2)) << 16; }
template<class Reader> bool exact(Reader &reader, uint8_t *out, size_t size) {
  while (size) { int n=reader(out,size); if(n<=0 || size_t(n)>size) return false; out+=n;size-=n; }
  return true;
}
// RIFF chunks can include LIST/JUNK and extended fmt chunks; audio need not start at byte 44.
template<class Reader> bool header(Reader &reader, uint32_t &bytes) {
  uint8_t b[32]; bool format=false; uint32_t metadata=0;
  if(!exact(reader,b,12) || memcmp(b,"RIFF",4) || memcmp(b+8,"WAVE",4)) return false;
  for(unsigned chunks=0; chunks<64; ++chunks) {
    if(!exact(reader,b,8)) return false;
    uint32_t n=le32(b+4);
    if(!memcmp(b,"data",4)) {
      if(!format || !n || (n&1) || n>64u*1024u*1024u) return false;
      bytes=n; return true;
    }
    bool fmt=!memcmp(b,"fmt ",4);
    if(n>65536 || metadata>65536-n) return false;
    metadata+=n;
    uint32_t left=n;
    if(fmt) {
      if(n<16 || !exact(reader,b,16)) return false;
      if(le16(b)!=1 || le16(b+2)!=1 || le32(b+4)!=16000 ||
         le32(b+8)!=32000 || le16(b+12)!=2 || le16(b+14)!=16) return false;
      format=true;left-=16;
    }
    left += n&1;
    while(left) {size_t part=std::min<size_t>(left,sizeof(b));if(!exact(reader,b,part))return false;left-=part;}
  }
  return false;
}
inline uint8_t encode(int16_t sample, uint32_t index, uint32_t total, float volume) {
  if(!std::isfinite(volume))volume=0;
  volume=std::max(0.0f,std::min(1.0f,volume));
  float fade=std::min(1.0f,std::min(float(index)/640.0f,float(total-1-index)/640.0f));
  int code=128+int(std::lround(float(sample)*volume*fade/256.0f));
  return uint8_t(std::max(0,std::min(255,code)));
}
}  // namespace shower_pcm

namespace shower_pcm {
// 16 kHz PCM -> 32 kHz DAC: avoid low-rate APLL without doubling music pitch/speed.
class Upsampler {
 public:
  void sample(int16_t current, uint32_t frame, uint32_t total, float volume, uint8_t *out) {
    int16_t midpoint = int16_t((int32_t(previous_) + int32_t(current)) / 2);
    out[0] = quantize(midpoint, frame * 2, total * 2, volume);
    out[1] = quantize(current, frame * 2 + 1, total * 2, volume);
    previous_ = current;
  }
 private:
  uint8_t quantize(int16_t sample, uint32_t index, uint32_t total, float volume) {
    if(!std::isfinite(volume))volume=0;
    volume=std::max(0.0f,std::min(1.0f,volume));
    float fade=std::min(1.0f,std::min(float(index)/640.0f,float(total-1-index)/640.0f));
    float target=128.0f+float(sample)*volume*fade/256.0f;
    if(target==128.0f){error_=0;return 128;}
    float shaped=target+error_;
    int rounded=int(std::lround(shaped));
    int code=std::max(0,std::min(255,rounded));
    error_=code==rounded ? shaped-code : 0.0f;
    return uint8_t(code);
  }
  int16_t previous_ = 0;
  float error_ = 0.0f;  // First-order error feedback moves quantization noise upward in frequency.
};
inline void transition(uint8_t *out, size_t count, uint8_t from, uint8_t to) {
  for(size_t i=0;i<count;++i) out[i]=uint8_t(int(from)+(int(to)-int(from))*int(i+1)/int(count));
}
}
