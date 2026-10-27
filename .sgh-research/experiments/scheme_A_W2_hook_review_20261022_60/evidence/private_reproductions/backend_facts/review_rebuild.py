from pathlib import Path
import hashlib, json, os, shlex, subprocess
ROOT=Path('/home/trevor/USV/.sgh-research/experiments/scheme_A_W2_pre_wiring_review_20261022_59/implementation/w2_author/worker')
OUT=Path('/tmp/w2_boundary_backend_review__imuqqm4')
BUILD=Path('/tmp/w2build')
base=(OUT/'review.cpp').read_text()
extra=r"""
class AdvancingOneShotReader final : public w2_gate::Reader {
 public:
  AdvancingOneShotReader(Identity id,TestClock &clock):id_(id),clock_(clock){}
  long read_some(uint8_t *buf,size_t n,int64_t,int64_t *elapsed)override{
   uint8_t frame[w2_gate::kFrameBytes];w2_gate::encode_release(frame,id_);
   const size_t take=std::min(n,w2_gate::kFrameBytes);std::memcpy(buf,frame,take);
   clock_.now+=200000000; if(elapsed)*elapsed=200000000;return long(take);
  }
 private:Identity id_;TestClock &clock_;
};
TEST(W2Review, MatchingBackendReleaseAfterJobDeadlineNeverStartsNativeCall) {
 TestClock clock; const auto initial=clock.now; const auto deadline=initial+150000000;
 Identity id{1,2,1,7}; AdvancingOneShotReader reader(id,clock);Gate gate(&reader,id,1000000000);
 BoundaryConfig cfg;cfg.job_id=2;cfg.ordinal=1;cfg.job_deadline_ns=deadline;cfg.wait_budget_ns=1000000000;
 Boundary boundary(&gate,cfg,[&]{return clock.now;});
 owned_cold::Backend backend(params(),binding(),true,[&]{return clock.now;});backend.attach_boundary(&boundary,[]{return false;});
 backend.set_applied_control(Eigen::Vector2d::Zero());
 EXPECT_THROW(backend.solve_owned(cold_start_job(2,deadline)),std::runtime_error);
 const auto rec=boundary.record();const auto event=backend.last_policy_event();
 EXPECT_TRUE(rec.released);EXPECT_EQ(rec.disposition,Disposition::kExpired);
 EXPECT_FALSE(rec.actual_native_invoked);EXPECT_EQ(rec.past_deadline_ns,50000000);
 EXPECT_TRUE(backend.terminal());EXPECT_EQ(event.at("backend_entries_started"),0);
 EXPECT_EQ(event.at("backend_entries_completed"),0);
 std::cout<<"W2_REVIEW_EXPIRED_FACTS "<<Json{{"job_id",2},{"ordinal",1},{"initial_ns",initial},{"job_deadline_ns",deadline},{"boundary",w2_boundary_json(rec)},{"terminal",backend.terminal()},{"backend_entries_started",event.at("backend_entries_started")},{"backend_entries_completed",event.at("backend_entries_completed")}}.dump()<<std::endl;
}
"""
src=OUT/'review_v2.cpp';src.write_text(base+extra)
flags={}
flags_file=BUILD/'CMakeFiles/test_w2_backend_wiring.dir/flags.make'
link_file=BUILD/'CMakeFiles/test_w2_backend_wiring.dir/link.txt'
for l in flags_file.read_text().splitlines():
 if l.startswith('CXX_') and ' = ' in l:
  k,v=l.split(' = ',1);flags[k]=shlex.split(v)
link=shlex.split(link_file.read_text());idx=link.index('CMakeFiles/test_w2_backend_wiring.dir/worker/test_w2_backend_wiring.cpp.o')
libs=[str(BUILD/x) if x.startswith('gtest/') else x for x in link[idx+3:]]
cmd=['/usr/bin/c++',*flags['CXX_DEFINES'],*flags['CXX_INCLUDES'],*flags['CXX_FLAGS'],'-MD','-MF',str(OUT/'review_v2.d'),str(src),'-o',str(OUT/'review_v2'),*libs]
env=os.environ.copy();env['LD_LIBRARY_PATH']='/home/trevor/acados/lib:/home/trevor/.local/lib/python3.12/site-packages/casadi:/opt/ros/jazzy/lib:/home/trevor/USV/usv_mpc_ws/install/usv_research_interfaces/lib'
r=subprocess.run(cmd,capture_output=True,text=True);(OUT/'build_v2.log').write_text(r.stdout+r.stderr)
record={'schema':'W2-boundary-backend-private-review-v2','author_tree_edited':False,'ROS_run':False,'cwd':os.getcwd(),'compile_and_link_argv':cmd,'build_rc':r.returncode,'runtime_environment_subset':{'LD_LIBRARY_PATH':env['LD_LIBRARY_PATH']}}
if r.returncode==0:
 run=[str(OUT/'review_v2'),'--gtest_filter=W2Review.*'];record['run_argv']=run
 q=subprocess.run(run,capture_output=True,text=True,env=env,timeout=60);(OUT/'run_v2.log').write_text(q.stdout+q.stderr);record['run_rc']=q.returncode
 for line in q.stdout.splitlines():
  if line.startswith('W2_REVIEW_EXPIRED_FACTS '):record['matching_expired_backend_observation']=json.loads(line.split(' ',1)[1])
 record['output_tail']=q.stdout[-7000:]
 deps=shlex.split((OUT/'review_v2.d').read_text().replace('\\\n',' ').split(': ',1)[1]);record['compile_dependency_count']=len(deps)
 def pin(p):
  p=Path(p);b=p.read_bytes();return {'path':str(p),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
 record['compile_dependencies']=[pin(p) for p in deps if Path(p).is_file()]
 record['link_input_files']=[pin(p) for p in libs if Path(p).is_file()]
 record['review_artifacts']=[pin(p) for p in [src,OUT/'review_v2',OUT/'run_v2.log',OUT/'build_v2.log',flags_file,link_file,Path(__file__)]]
(OUT/'review_reproducibility_v2.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps({'evidence_json':str(OUT/'review_reproducibility_v2.json'),'build_rc':r.returncode,'run_rc':record.get('run_rc'),'expired_observation':record.get('matching_expired_backend_observation'),'dependencies':record.get('compile_dependency_count')}))
print(record.get('output_tail',(r.stdout+r.stderr)[-2000:]))
