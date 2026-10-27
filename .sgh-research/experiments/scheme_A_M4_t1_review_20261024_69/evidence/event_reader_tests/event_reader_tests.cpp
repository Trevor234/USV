#include <gtest/gtest.h>
#include <nlohmann/json.hpp>
#include <chrono>
#include <thread>
#include <fstream>
#include <filesystem>
namespace p1 {using Json=nlohmann::json;}
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
