#!/usr/bin/env python3
"""Derive test-only fixes; leave batch68 and the real Regulator untouched."""
from pathlib import Path
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]
B68 = ROOT.parent / 'scheme_A_M4_t1_component_wiring_20261024_68'
TARGET = ROOT / 'implementation/reviewed_harness'
(TARGET / 'tests').mkdir(parents=True)
shutil.copy2(B68 / 'implementation/CMakeLists.txt', TARGET / 'CMakeLists.txt')
original = B68 / 'implementation/tests/test_current_candidate_reference_clock.cpp'
text = original.read_text()
old = '''      if(line.find("\\\""+type+"\\\"")==std::string::npos)continue;
      try{last=p1::Json::parse(line);++n;}catch(...){}'''
new = '''      try{auto row=p1::Json::parse(line);
        if(row.value("type",std::string{})==type){last=std::move(row);++n;}
      }catch(const p1::Json::parse_error&){}'''
assert text.count(old) == 1
text = text.replace(old, new, 1)
helper = r'''
// Bind visibility to this invocation, full Job identity, and the actual event
// type. The pad is only an aid to visibility; it is never the acknowledgement.
static p1::Json wait_current_registration(const std::string &file,
    const p1::Json &expected_job,int64_t invocation_ns) {
  const auto deadline=std::chrono::steady_clock::now()+std::chrono::milliseconds(200);
  do {
    std::ifstream in(file);std::string line;
    while(std::getline(in,line)) {
      try {
        auto row=p1::Json::parse(line);
        if(row.value("type",std::string{})=="candidate_registration" &&
           row.contains("job") && row.at("job")==expected_job &&
           row.value("ready_commit_ns",int64_t(0))>=invocation_ns)
          return row;
      }catch(const p1::Json::parse_error&){}
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(2));
  } while(std::chrono::steady_clock::now()<deadline);
  return {};
}
'''
needle = '\nclass C33MatrixAccess {'
assert text.count(needle) == 1
text = text.replace(needle, helper + needle, 1)
old = '''  seed_echo(r,j);r.candidate(c);flush_pad(r);
  auto ev=wait_event(sink,"candidate_registration",1);
  if(ev.is_null()){reason="<no_event>";return false;}'''
new = '''  const auto invocation_ns=p1::monotonic_ns();
  seed_echo(r,j);r.candidate(c);flush_pad(r);
  auto ev=wait_current_registration(sink,p1::job_json(j),invocation_ns);
  if(ev.is_null()){reason="<no_current_registration>";return false;}'''
assert text.count(old) == 1
text = text.replace(old, new, 1)
old = '''  EXPECT_TRUE(C33MatrixAccess::register_candidate(*reg,sink_file,next,C33MatrixAccess::candidate_msg(next),reason))<<reason;
}'''
new = '''  EXPECT_TRUE(C33MatrixAccess::register_candidate(*reg,sink_file,next,C33MatrixAccess::candidate_msg(next),reason))<<reason;
  EXPECT_TRUE(C33MatrixAccess::candidate_present(*reg));
  EXPECT_TRUE(C33MatrixAccess::admission_slots(*reg,1));
}'''
assert text.count(old) == 1
text = text.replace(old, new, 1)
needle = '''  EXPECT_EQ(reason,"shape_or_time_contract");
  EXPECT_TRUE(C33MatrixAccess::admission_slots(*reg,0));
}'''
replacement = '''  EXPECT_EQ(reason,"shape_or_time_contract");
  auto unavailable=j;unavailable.job_id=4;
  EXPECT_FALSE(C33MatrixAccess::register_candidate(*reg,sink_file,unavailable,
    C33MatrixAccess::candidate_msg(unavailable,1.0,false,true,true),reason));
  EXPECT_EQ(reason,"solver_failed");
  EXPECT_TRUE(C33MatrixAccess::admission_slots(*reg,0));
}'''
assert text.count(needle) == 1
text = text.replace(needle, replacement, 1)
target = TARGET / 'tests/test_current_candidate_reference_clock.cpp'
with target.open('x') as stream:
    stream.write(text)
with (ROOT / 'evidence/reviewed_harness_derivation_v1.json').open('x') as stream:
    json.dump({'original': str(original), 'original_sha256': hashlib.sha256(original.read_bytes()).hexdigest(),
               'derived': str(target), 'derived_sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
               'changes': ['exact event type', 'full Job plus invocation timestamp binding',
                   '200ms bounded visibility wait', 'new-Job recovery state assertions',
                   'prediction_available=false alone is rejected'],
               'production_Regulator_changed': False, 'batch68_changed': False}, stream, indent=2)
    stream.write('\n')
print(json.dumps({'prepared': True, 'target': str(target)}))
