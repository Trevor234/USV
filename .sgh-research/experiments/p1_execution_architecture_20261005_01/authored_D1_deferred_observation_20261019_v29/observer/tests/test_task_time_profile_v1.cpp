// SPDX-License-Identifier: MIT
#include "task_time_profile_v1.hpp"
#include <iostream>
#include <limits>
#include <stdexcept>
using namespace task_time_reference;
int main(){unsigned checks=0;auto check=[&](bool b,const char *m){++checks;if(!b)throw std::runtime_error(m);};
 Binding b{{2,1,1,1,1},"run","boot",std::string(64,'a'),std::string(64,'b'),std::string(64,'c'),std::string(64,'d')};
 usv_mpc::ReferenceInput input;input.path_stamp=input.profile_stamp={100,0};
 for(int k=0;k<=200;++k){input.path.push_back({.05*(.2*k),0.,0.});input.profile.push_back({.05,0.,0.,.2*k});}
 usv_mpc::Vector6d x=usv_mpc::Vector6d::Zero();Epoch epoch;
 auto p=epoch.propose(b,100000000000LL,x,input);check(p.valid&&p.first,"first proposal valid");check(!epoch.active(),"prepare cannot bind epoch");
 for(int k=0;k<8;++k){auto pending=epoch.propose(b,100000000000LL+k*200000000LL,x,input);check(pending.valid&&!epoch.active(),"failed caller guards leave epoch unset");}
 check(p.reference==reference_candidate::build(x,input).reference,"first G T exactly equal");
 check(!epoch.commit(p,0,1)&&!epoch.active(),"failed Job id cannot commit");check(!epoch.commit(p,1,0)&&!epoch.active(),"failed completion cannot commit");
 check(epoch.commit(p,4,1000),"actual completion can bind nonfirst attempted Job id");check(epoch.active(),"bound after commit");
 check(epoch.anchor()->first_job_id==4&&epoch.anchor()->first_target_sim_ns==100000000000LL&&epoch.anchor()->commit_ns==1000,"exact first successful tuple");
 check(!epoch.commit(p,5,1001),"duplicate tentative first proposal rejected");
 auto q=epoch.propose(b,101000000000LL,x,input);check(q.valid&&!q.first&&q.profile_t0==1.,"fixed target time advancement");check(q.reference(0,0)==.05,"reference moves while target holds");
 check(q.geometric.profile_t0==0.,"geometric diagnostic stays independent");check(q.reference(3,0)==.05&&q.reference(4,0)==0.,"actual speed and sway preserved");
 check(epoch.commit(q,5,1002),"second completion");check(epoch.anchor()->first_job_id==4&&epoch.anchor()->commit_ns==1000,"epoch does not reanchor");
 check(!epoch.propose(b,101000000000LL,x,input).valid,"duplicate target time rejected");check(!epoch.propose(b,100500000000LL,x,input).valid,"clock backward rejected");
 for(size_t k=0;k<5;++k){auto bad=b;bad.version[k]++;check(!epoch.propose(bad,102000000000LL,x,input).valid,"generation or clock mismatch rejects");Epoch copy=epoch;copy.invalidate_if_changed(bad);check(copy.terminal(),"binding mismatch terminal");check(!copy.propose(b,102000000000LL,x,input).valid,"cannot silently recover old epoch");}
 for(size_t k=0;k<6;++k){auto bad=b;std::string *values[]={&bad.run,&bad.boot,&bad.contract,&bad.nominal,&bad.path,&bad.profile};values[k]->push_back('x');check(!epoch.propose(bad,102000000000LL,x,input).valid,"identity content mismatch rejects");}
 auto refreshed=input;refreshed.path_stamp=refreshed.profile_stamp={101,500000000};auto refresh=epoch.propose(b,102000000000LL,x,refreshed);check(refresh.valid&&refresh.anchor.first_target_sim_ns==100000000000LL,"new exact paired stamp retains epoch");
 refreshed.profile_stamp={101,400000000};check(!epoch.propose(b,102000000000LL,x,refreshed).valid,"unpaired stamp rejects");
 check(!epoch.propose(b,137000000000LL,x,input).valid,"horizon coverage rejects");
 for(int k=0;k<5;++k){auto bad=input;if(k==0)bad.path.pop_back();if(k==1)bad.profile[1][3]=1e-12;if(k==2)bad.path[4][0]+=.001;if(k==3)bad.profile[2][0]=.1;if(k==4)bad.profile[1][3]=std::numeric_limits<double>::quiet_NaN();check(!epoch.propose(b,102000000000LL,x,bad).valid,"static domain corruption rejects");}
 Epoch terminal=epoch;terminal.invalidate("clock_reset");check(terminal.terminal()&&!terminal.commit(refresh,6,1003),"terminal cannot commit queued proposal");
 auto mutated=refresh;mutated.anchor.first_target_sim_ns++;check(!epoch.commit(mutated,6,1003),"stale epoch tuple cannot commit");
 auto nan=x;nan[0]=std::numeric_limits<double>::quiet_NaN();check(!epoch.propose(b,102000000000LL,nan,input).valid,"target nonfinite rejects");
 for(int k=0;k<21;++k){check(q.reference(3,k)==p.reference(3,k)&&q.reference(4,k)==p.reference(4,k)&&q.reference(5,k)==p.reference(5,k),"all velocity references remain exact");}
 std::cout<<"task-time epoch checks="<<checks<<" passed; pure component; no ROS calls\n";
}
