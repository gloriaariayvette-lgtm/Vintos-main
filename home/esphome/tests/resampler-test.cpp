#include "wav_pcm.h"
#include <cassert>
#include <vector>
#include <iostream>
constexpr double pi=3.141592653589793;
std::vector<uint8_t> render(float gain) {
  std::vector<uint8_t> out(32000);shower_pcm::Upsampler r;
  for(unsigned i=0;i<16000;++i)r.sample(int16_t(std::lround(16000*std::sin(2*pi*1000*i/16000))),i,16000,gain,out.data()+2*i);
  return out;
}
int main(){
 auto a=render(1),b=render(.5f);
 // A one-second 16 kHz input stays one second and 1 kHz at the 32 kHz DAC.
 assert(a.size()==32000);int crossings=0;double energy=0,half_energy=0;
 for(unsigned i=3200;i<28800;++i){
  if(a[i-1]<128&&a[i]>=128)++crossings;
  energy+=std::pow(int(a[i])-128,2);half_energy+=std::pow(int(b[i])-128,2);
 }
 assert(crossings>=795&&crossings<=805);
 assert(std::abs(std::sqrt(half_energy/energy)-.5)<.02);
 assert(a.front()==128&&a.back()==128);
 uint8_t ramp[640];shower_pcm::transition(ramp,640,220,128);
 assert(ramp[639]==128);for(int i=1;i<640;++i)assert(ramp[i]<=ramp[i-1]);
 shower_pcm::transition(ramp,640,20,128);assert(ramp[639]==128);for(int i=1;i<640;++i)assert(ramp[i]>=ramp[i-1]);
 std::cout<<"PASS: duration, pitch, gain, start/end fade, monotonic midpoint transition\n";
}
