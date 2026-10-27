#include "/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_rnw_s4_owned_20261025_119/implementation/t2_author/fixture/resume_stamp_mapping_v1.hpp"
#include <iostream>
int main(){
 resume_mapping::Mapping m;
 const int64_t published_stamp=100000000000LL,old_target=1000000000LL,old_receive=1001000000LL;
 const int64_t resume_target=2500000000LL,resume_receive=2515000000LL;
 const int64_t pre_publish=2510000000LL,post_publish=2520000000LL;
 resume_mapping::note_published(m,published_stamp,old_target);resume_mapping::arm_resume(m);
 auto new_stamp=resume_mapping::step_stamp(m,false,published_stamp,resume_target,resume_target-20000000LL);
 auto previous_history=published_stamp+(pre_publish-old_receive);
 auto next_history=new_stamp+(post_publish-resume_receive);
 std::cout<<"within_cap="<<(resume_target-old_target<resume_mapping::CATCH_UP_CAP_NS)<<" previous_history="<<previous_history<<" next_history="<<next_history<<" backwards_ns="<<previous_history-next_history<<"\n";
}
