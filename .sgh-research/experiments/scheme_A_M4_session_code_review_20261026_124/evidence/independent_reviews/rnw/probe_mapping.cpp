#include "/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_rnw_s4_owned_20261025_119/implementation/t2_author/fixture/resume_stamp_mapping_v1.hpp"
#include <iostream>
#include <limits>
int main(int argc,char **argv){
 resume_mapping::Mapping m;
 if(argc>1){
  resume_mapping::note_published(m,std::numeric_limits<int64_t>::max()-10,100);
  resume_mapping::arm_resume(m);
  std::cout<<resume_mapping::step_stamp(m,false,m.published_stamp_ns,200,190)<<"\n";
 } else {
  resume_mapping::note_published(m,100000000000LL,1000000000LL);
  resume_mapping::arm_resume(m);
  auto projected_before=100000000000LL+6000000000LL;
  auto resumed=resume_mapping::step_stamp(m,false,100000000000LL,7020000000LL,7000000000LL);
  std::cout<<"pre_resume_projected="<<projected_before<<" resumed="<<resumed<<" projected_backstep="<<(projected_before-resumed)<<"\n";
 }
}
