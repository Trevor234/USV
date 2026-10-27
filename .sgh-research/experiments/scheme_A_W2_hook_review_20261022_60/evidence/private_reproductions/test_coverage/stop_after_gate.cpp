#include <cstring>
#include <iostream>
#include "w2_native_boundary.hpp"
struct R: w2_gate::Reader {
 w2_gate::Identity id;
 explicit R(w2_gate::Identity x):id(x){}
 long read_some(uint8_t*b,size_t n,int64_t,int64_t*e) override {uint8_t f[w2_gate::kFrameBytes];w2_gate::encode_release(f,id);std::memcpy(b,f,n);*e=0;return n;}
};
int main(){w2_gate::Identity id{1,2,1,3};R reader(id);w2_gate::Gate gate(&reader,id,1000000);w2_wire::BoundaryConfig cfg{2,1,1000000,1000000};w2_wire::Boundary b(&gate,cfg,[]{return int64_t(0);});b.set_clock([]{return int64_t(0);});int loads=0;bool allowed=b.enter(1,2,[&]{return ++loads>=3;});std::cout<<w2_boundary_json(b.record()).dump()<<"\n";return allowed||!b.record().released||!b.record().stop_at_release||b.record().disposition!=w2_wire::Disposition::kStopped;}
