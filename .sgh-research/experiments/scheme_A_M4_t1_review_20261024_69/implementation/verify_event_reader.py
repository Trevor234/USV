#!/usr/bin/env python3
"""Compile the exact reviewed event-reader body in a small non-ROS test."""
from pathlib import Path
import hashlib
import json
import subprocess

ROOT = Path(__file__).resolve().parents[1]
TEST = ROOT / 'implementation/reviewed_harness/tests/test_current_candidate_reference_clock.cpp'
OUT = ROOT / 'evidence/event_reader_tests'


def main():
    OUT.mkdir()
    text = TEST.read_text()
    start = text.index('static p1::Json wait_current_registration(')
    end = text.index('\nclass C33MatrixAccess', start)
    body = text[start:end]
    source = r'''#include <gtest/gtest.h>
#include <nlohmann/json.hpp>
#include <chrono>
#include <thread>
#include <fstream>
#include <filesystem>
namespace p1 {using Json=nlohmann::json;}
'''+body+r'''
static std::string stream_file(const p1::Json &rows){
 const auto name=::testing::UnitTest::GetInstance()->current_test_info()->name();
 auto file=std::filesystem::path(TEST_OUTPUT)/name;
 std::ofstream stream(file);for(const auto&row:rows)stream<<row.dump()<<'\n';stream.close();return file;
}
static p1::Json row(int id,int task,int64_t ns,const std::string &type="candidate_registration"){
 return {{"type",type},{"job",{{"job_id",id},{"task_generation",task}}},
   {"ready_commit_ns",ns},{"accepted_registration",true},{"reason",""}};
}
TEST(EventReader, OldJob1CannotAcknowledgeMissingJob2){
 auto file=stream_file(p1::Json::array({row(1,1,300)}));
 EXPECT_TRUE(wait_current_registration(file,{{"job_id",2},{"task_generation",1}},200).is_null());
}
TEST(EventReader, SameJobBeforeInvocationIsStale){
 auto file=stream_file(p1::Json::array({row(2,1,100)}));
 EXPECT_TRUE(wait_current_registration(file,{{"job_id",2},{"task_generation",1}},200).is_null());
}
TEST(EventReader, CurrentExactJobAcknowledges){
 auto file=stream_file(p1::Json::array({row(2,1,201)}));
 auto result=wait_current_registration(file,{{"job_id",2},{"task_generation",1}},200);
 ASSERT_FALSE(result.is_null());EXPECT_EQ(result["job"]["job_id"],2);
}
TEST(EventReader, JobIDAloneDoesNotMatchAnotherTask){
 auto file=stream_file(p1::Json::array({row(2,2,201)}));
 EXPECT_TRUE(wait_current_registration(file,{{"job_id",2},{"task_generation",1}},200).is_null());
}
TEST(EventReader, MentionInAnotherRowIsNotTheEventType){
 auto value=row(2,1,201,"different_type");value["note"]="candidate_registration";
 auto file=stream_file(p1::Json::array({value}));
 EXPECT_TRUE(wait_current_registration(file,{{"job_id",2},{"task_generation",1}},200).is_null());
}
TEST(EventReader, FindsCurrentJobAfterOldRegistration){
 auto file=stream_file(p1::Json::array({row(1,1,100),row(2,1,201)}));
 auto result=wait_current_registration(file,{{"job_id",2},{"task_generation",1}},200);
 ASSERT_FALSE(result.is_null());EXPECT_EQ(result["ready_commit_ns"],201);
}
'''
    # The raw C++ literal above deliberately needs one backslash for newline.
    source = source.replace("'\\\\n'", "'\\n'")
    cpp = OUT / 'event_reader_tests.cpp'
    cpp.write_text(source)
    argv = ['g++', '-std=c++17', '-O0', '-g0', '-pthread',
        '-DTEST_OUTPUT="' + str(OUT) + '"', str(cpp), '-lgtest_main', '-lgtest',
        '-o', str(OUT / 'event_reader_tests')]
    build = subprocess.run(argv, capture_output=True, text=True, timeout=90)
    (OUT / 'compile.log').write_text(build.stdout + build.stderr)
    assert build.returncode == 0
    run = subprocess.run([str(OUT / 'event_reader_tests'), '--gtest_output=json:' + str(OUT / 'gtest.json')],
                         capture_output=True, text=True, timeout=10)
    (OUT / 'run.log').write_text(run.stdout + run.stderr)
    doc = json.loads((OUT / 'gtest.json').read_text())
    passed = run.returncode == 0 and doc['tests'] == 6 and doc['failures'] == doc['errors'] == 0
    report = {'tests': 6, 'passed': passed, 'ROS_initialized': False,
        'body_extracted_from': str(TEST), 'body_sha256': hashlib.sha256(body.encode()).hexdigest(),
        'source_sha256': hashlib.sha256(cpp.read_bytes()).hexdigest(), 'scope': 'Exact reader helper body; not Regulator execution'}
    with (OUT / 'verification_v1.json').open('x') as stream:
        stream.write(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
    return 0 if passed else 2


if __name__ == '__main__':
    raise SystemExit(main())
