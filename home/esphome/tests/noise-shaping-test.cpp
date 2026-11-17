#include "wav_pcm.h"
#include <vector>
#include <cassert>
#include <iostream>
constexpr double PI=3.141592653589793;
int main(){
 const int n=64000;std::vector<double> plain(n),shaped(n);shower_pcm::Upsampler up;
 int16_t prev=0;
 for(int i=0;i<n/2;++i){
  int16_t current=std::lround(1600*std::sin(2*PI*997*i/16000)+900*std::sin(2*PI*2713*i/16000));
  int16_t mid=int16_t((int(prev)+int(current))/2);uint8_t out[2];up.sample(current,i,n/2,1,out);
  for(int j=0;j<2;++j){
   int k=i*2+j;int16_t sample=j?current:mid;
   double fade=std::min(1.0,std::min(k/640.0,(n-1-k)/640.0));
   double target=128+sample*fade/256.0;
   plain[k]=int(shower_pcm::encode(sample,k,n,1))-target;
   shaped[k]=int(out[j])-target;
  }prev=current;
 }
 // Independent 63-tap 3.5 kHz lowpass measures error in the speech band.
 double taps[63],sum=0;
 for(int i=0;i<63;++i){int x=i-31;taps[i]=(x?std::sin(2*PI*3500*x/32000)/(PI*x):2.0*3500/32000)*(0.5-0.5*std::cos(2*PI*i/62));sum+=taps[i];}
 double a=0,b=0;
 for(int i=3200;i<n-3200;++i){double x=0,y=0;for(int j=0;j<63;++j){x+=plain[i-j]*taps[j]/sum;y+=shaped[i-j]*taps[j]/sum;}a+=x*x;b+=y*y;}
 double improvement=10*std::log10(a/b);std::cout<<"Speech-band quantization-noise reduction: "<<improvement<<" dB\n";assert(improvement>5);
 shower_pcm::Upsampler quiet;uint8_t out[2];for(int i=0;i<32000;++i){quiet.sample(0,i,32000,1,out);assert(out[0]==128&&out[1]==128);}
 std::cout<<"PASS: speech-band error reduced; digital silence stays exact midpoint\n";
}
