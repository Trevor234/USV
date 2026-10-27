#include "resume_stamp_mapping_v1.hpp"
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <nlohmann/json.hpp>
using namespace resume_mapping;
using Json=nlohmann::json;
Json assertions=Json::array();bool passed=true;
void check(bool v,const char*name,Json fact=nullptr){assertions.push_back({{"name",name},{"passed",v},{"observed",fact}});passed&=v;}
StepResult resume(Mapping&m,int64_t stamp,int64_t old,int64_t now){note_published(m,stamp,old);arm_resume(m);return step_stamp_checked(m,false,stamp,now,now>20000000?now-20000000:0);}
void test(const std::string&id){
 if(id=="B2V-01-LEGAL"){
  Mapping m;auto r=resume(m,100000000000LL,1000000000,2500000000);
  check(r.normal_allowed()&&r.stamp_ns==101500000000LL&&!m.resume_pending,"published_pair_formula_once");
  auto next=step_stamp_checked(m,false,r.stamp_ns,2520000000,2500000000);
  check(next.normal_allowed()&&next.stamp_ns-r.stamp_ns==20000000,"ordinary_next_step_not_double_counted");
 }else if(id=="B2V-16-NO-HOLD"){
  Mapping m;int64_t old=0,s=0,expected=0;bool equal=true;
  for(int i=1;i<=100;++i){int64_t t=int64_t(i)*20000000;expected+=old?t-old:100000000000LL;
   auto r=step_stamp_checked(m,false,s,t,old);equal&=r.normal_allowed()&&r.stamp_ns==expected;s=r.stamp_ns;old=t;}
  check(equal,"ordinary_path_original_formula_preserved");
 }else if(id=="B2V-17a-MAX"){
  Mapping m;auto r=resume(m,std::numeric_limits<int64_t>::max()-10,1000,1100);
  check(!r.valid&&std::string(r.reason)=="stamp_overflow","resume_overflow_rejected");
  check(m.resume_pending,"invalid_mapping_does_not_consume_resume");
 }else if(id=="B2V-17b-MIN"){
  Mapping m;note_published(m,100,1);arm_resume(m);
  auto r=step_stamp_checked(m,false,100,std::numeric_limits<int64_t>::min(),0);
  check(!r.valid&&std::string(r.reason)=="elapsed_overflow","elapsed_subtraction_underflow_rejected");
 }else if(id=="B2V-17c-CAP-EDGE"){
  Mapping a,b,c;auto below=resume(a,100000000000LL,1000000000LL,1000000000LL+CATCH_UP_CAP_NS-1);
  auto edge=resume(b,100000000000LL,1000000000LL,1000000000LL+CATCH_UP_CAP_NS);
  auto above=resume(c,100000000000LL,1000000000LL,1000000000LL+CATCH_UP_CAP_NS+1);
  check(below.normal_allowed()&&edge.normal_allowed()&&!edge.capped,"cap_exact_edge_not_clipped");
  check(above.valid&&above.capped&&!above.normal_allowed(),"one_ns_above_cap_explicitly_outside_normal");
 }else if(id=="B2V-17d-PLUS"){
  Mapping m;auto r=step_stamp_checked(m,false,std::numeric_limits<int64_t>::max()-10,1100,1000);
  check(!r.valid&&std::string(r.reason)=="stamp_overflow","ordinary_addition_overflow_rejected");
 }else if(id=="B2V-18-UBSAN"){
  int64_t value=0;check(!add64(INT64_MAX,1,value)&&!add64(INT64_MIN,-1,value),"checked_add_extremes");
  check(!subtract64(INT64_MIN,1,value)&&!subtract64(INT64_MAX,-1,value),"checked_subtract_extremes");
  check(add64(INT64_MIN,INT64_MAX,value)&&value==-1,"representable_signed_sum_kept");
  check(subtract64(INT64_MIN,INT64_MIN,value)&&value==0,"representable_signed_subtraction_kept");
 }else if(id=="B2V-19-CAP"){
  Mapping m;auto r=resume(m,100000000000LL,1000000000,7000000000);
  check(r.valid&&r.capped&&r.stamp_ns==104900000000LL,"cap_value_explicit");
  check(!r.normal_allowed(),"cap_is_not_normal_recovery");
 }else if(id=="B2V-20a-LONG-HOLD"){
  Mapping m;auto r=resume(m,100000000000LL,1000000000,7000000000);
  const auto backward=106000000000LL-r.stamp_ns;
  check(r.capped&&backward==1100000000LL,"long_hold_limitation_1100000000ns",backward);
 }else if(id=="B2V-20b-RX-SKEW"){
  Mapping m;auto r=resume(m,100000000000LL,1000000000,2500000000);
  const int64_t previous=100000000000LL+(2510000000LL-1001000000LL);
  const int64_t next=r.stamp_ns+(2520000000LL-2515000000LL);const auto back=previous-next;
  check(r.normal_allowed()&&back==4000000,"legal_receive_skew_still_regresses_4000000ns",back);
 }else if(id=="B2V-21-ROS-RANGE"){
  check(ros_time_representable(100000000000LL)&&!ros_time_representable(INT64_MAX),"ROS_seconds_range_checked_before_publish");
 }else throw std::runtime_error("unknown case");
}
int main(int argc,char**argv){try{
 if(argc!=3)throw std::runtime_error("case/output");std::filesystem::path out(argv[2]);
 if(std::filesystem::exists(out))throw std::runtime_error("create-only");std::filesystem::create_directories(out);
 test(argv[1]);Json d={{"case",argv[1]},{"passed",passed},{"assertions",assertions},{"stage_qualified",false},{"ROS_initialized",false}};
 std::ofstream f(out/"result.json");f<<d.dump(2)<<'\n';return passed?0:2;
 }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 3;}}
