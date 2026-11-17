#include "steam_signal.h"
#include <cassert>
#include <cmath>
#include <iostream>
int main() {
 house_steam::Signal dry;int state=-1;uint32_t now=0;
 for(;now<300000;now+=2000) { state=dry.update(3.16f,8,now);assert(state!=1); }
 // A complete low rail once per window cannot trigger steam.
 for(unsigned i=0;i<150;i++,now+=2000) {state=dry.update(i%15==0?.132f:3.16f,8,now);assert(state!=1);}
 const float measured[]={2.679f,3.16f,3.16f,3.16f,3.16f,3.16f,2.093f,2.759f,3.16f,1.846f,3.16f,3.16f,3.16f,3.16f,3.16f};
 for(unsigned i=0;i<90;i++,now+=2000)state=dry.update(measured[i%15],8,now);
 assert(state==1);
 for(unsigned i=0;i<10;i++,now+=2000)assert(dry.update(3.16f,8,now)==1);
 for(unsigned i=0;i<60;i++,now+=2000)state=dry.update(3.16f,8,now);
 assert(state==0);assert(dry.update(NAN,8,now)==-1);assert(std::isnan(dry.score()));
 house_steam::Signal paused;
 for(unsigned i=0;i<100;i++)assert(paused.update(measured[i%15],100,i*2000)!=1);
 house_steam::Signal wrap;now=0xffffc000;
 for(unsigned i=0;i<100;i++,now+=2000)state=wrap.update(measured[i%15],8,now);
 assert(state==1);
 std::cout<<"PASS: dry, isolated rail spikes, measured shower trace, sustained release, invalid input, pause, timer wrap\n";
}
