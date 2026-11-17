#include "wav_pcm.h"
#include <vector>
#include <cassert>
#include <iostream>
#include <limits>
using V=std::vector<uint8_t>;
void u16(V&v,unsigned n){v.push_back(n&255);v.push_back((n>>8)&255);}
void u32(V&v,unsigned n){u16(v,n&65535);u16(v,n>>16);}
void id(V&v,const char*s){v.insert(v.end(),s,s+4);}
V wav(bool meta=false,bool extended=false){
 V v;id(v,"RIFF");u32(v,0);id(v,"WAVE");id(v,"fmt ");u32(v,extended?18:16);
 u16(v,1);u16(v,1);u32(v,16000);u32(v,32000);u16(v,2);u16(v,16);if(extended)u16(v,0);
 if(meta){id(v,"LIST");u32(v,5);for(int i=0;i<5;++i)v.push_back(90);v.push_back(0);}
 id(v,"data");u32(v,2048);v.resize(v.size()+2048,0);return v;
}
bool parse(V v,size_t part=1000){
 size_t at=0;auto read=[&](uint8_t*b,size_t n)->int{n=std::min(n,std::min(part,v.size()-at));memcpy(b,v.data()+at,n);at+=n;return n;};
 uint32_t bytes=0;bool ok=shower_pcm::header(read,bytes);
 if(ok){assert(bytes==2048);assert(v.size()-at==2048);}
 return ok;
}
int main(){
 assert(parse(wav()));assert(parse(wav(true)));assert(parse(wav(true,true),1));
 auto bad=wav();bad[22]=2;assert(!parse(bad)); // Stereo rejected.
 bad=wav();bad[24]=0;assert(!parse(bad)); // Wrong rate rejected.
 bad=wav();bad[34]=8;assert(!parse(bad)); // Wrong PCM depth rejected.
 bad=wav();bad[20]=3;assert(!parse(bad)); // Float rejected.
 bad=wav();bad[0]='X';assert(!parse(bad));
 bad=wav();bad.resize(30);assert(!parse(bad));
 bad=wav();bad[40]=1;assert(!parse(bad)); // Odd byte count rejected.
 for(int s=-32768;s<=32767;s+=257){
  assert(shower_pcm::encode(s,0,16000,.25f)==128);
  assert(shower_pcm::encode(s,15999,16000,.25f)==128);
  assert(shower_pcm::encode(s,8000,16000,0)==128);
  assert(shower_pcm::encode(s,8000,16000,NAN)==128);
  auto x=shower_pcm::encode(s,8000,16000,.25f);assert(x>=96&&x<=160);
 }
 assert(shower_pcm::encode(32767,8000,16000,1)==255);
 assert(shower_pcm::encode(-32768,8000,16000,1)==0);
 std::cout<<"PASS: canonical/metadata/extended WAV, byte-fragmented reads, invalid/truncated formats, gain/ramp/saturation\n";
}
