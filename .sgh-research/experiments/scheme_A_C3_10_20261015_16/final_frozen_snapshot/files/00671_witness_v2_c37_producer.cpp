#include "witness_v2_c37_fixture.hpp"
#include <iostream>
#include <string_view>
int main(int argc,char **argv) {
  if(argc!=3){std::cerr<<"usage: witness_v2_c37_producer CASE CREATE_ONLY_JSON\n";return 2;}
  constexpr std::string_view cases[]={"accepted","all_rejected","accepted_then_rejected","append_rejected",
    "overflow","disabled","duplicate_submit","mismatched_ready","missing_ready","missing_close","failed_tick",
    "source_failure","duplicate_ready","startup_ready","wrong_ready_observation","header_invalid","after_close",
    "reversed_ticks","different_first_accepted"};
  bool allowed=false;for(const auto c:cases)if(c==argv[1])allowed=true;
  if(!allowed){std::cerr<<"unknown finite fixture case\n";return 2;}
  p1::Witness w(std::string_view(argv[1])!="disabled",c37_witness_fixture::header());
  c37_witness_fixture::populate(w,argv[1]);const auto s=w.summary();
  const bool written=w.write_terminal(argv[2]);
  std::cout<<"observation_complete="<<s.observation_complete<<" business_ready_observed="<<s.business_ready_observed
    <<" normal_contract_qualified="<<s.normal_contract_qualified<<" written="<<written<<'\n';
  return written?0:std::string_view(argv[1])=="disabled"?0:2;
}
