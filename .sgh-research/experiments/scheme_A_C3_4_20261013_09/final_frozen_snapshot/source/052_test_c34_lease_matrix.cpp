// SPDX-License-Identifier: MIT
#include <gtest/gtest.h>
#include <filesystem>
#include "c34_lease_access.hpp"

class C34LeaseMatrix:public ::testing::Test {
 protected:
  static void SetUpTestSuite(){int argc=0;rclcpp::init(argc,nullptr,rclcpp::InitOptions(),rclcpp::SignalHandlerOptions::None);}
  static void TearDownTestSuite(){rclcpp::shutdown();}
  std::unique_ptr<Regulator> r;std::string source;
  void SetUp()override{
    auto base=std::getenv("P1_C34_LEASE_NATIVE_DIR");std::filesystem::path dir=base?base:"/tmp/p1-C34-lease-native";
    std::filesystem::create_directories(dir);source=(dir/(std::string(::testing::UnitTest::GetInstance()->current_test_info()->name())+".jsonl")).string();
    if(std::filesystem::exists(source))throw std::runtime_error("native evidence exists");
    r=C34LeaseAccess::make(source);
  }
  void TearDown()override{C34LeaseAccess::close(*r);r.reset();}
  void send(const p1::Capability &m){C34LeaseAccess::callback(*r,m);}
  auto good(){return C34LeaseAccess::valid(*r);}
  auto state(){return C34LeaseAccess::state(*r);}
};
TEST_F(C34LeaseMatrix,ValidInvalidKeepsLastValid){auto a=good();send(a);auto before=state();a.backend="other";send(a);EXPECT_EQ(state(),before);}
TEST_F(C34LeaseMatrix,ValidForeignFatalKeepsLastValid){auto a=good();send(a);auto before=state();a.run_id="foreign";a.fatal=true;send(a);EXPECT_EQ(state(),before);}
TEST_F(C34LeaseMatrix,ResourceRejectedKeepsLastValid){auto a=good();send(a);auto before=state();a.reason=std::string(257,'x');send(a);EXPECT_EQ(state(),before);}
TEST_F(C34LeaseMatrix,MatchingFatalIsTerminal){auto a=good();send(a);auto before=state();a.fatal=true;send(a);EXPECT_EQ(state()["last_valid_ns"],before["last_valid_ns"]);EXPECT_EQ(state()["worker_unusable"],true);EXPECT_EQ(state()["worker_valid"],false);}
TEST_F(C34LeaseMatrix,MatchingChangedInvalidInstanceIsTerminal){auto a=good();send(a);auto before=state();a.worker_instance=std::string(64,'f');a.backend="other";send(a);EXPECT_EQ(state()["last_valid_ns"],before["last_valid_ns"]);EXPECT_EQ(state()["worker_unusable"],true);}
TEST_F(C34LeaseMatrix,ExactTimeoutCheckDoesNotExpire){send(good());auto before=state();C34LeaseAccess::check(*r,before["last_valid_ns"].get<int64_t>()+600000000);EXPECT_EQ(state(),before);}
TEST_F(C34LeaseMatrix,TimeoutPlusOneThenValidCannotRevive){auto a=good();send(a);auto before=state();C34LeaseAccess::check(*r,before["last_valid_ns"].get<int64_t>()+600000001);send(a);EXPECT_EQ(state()["last_valid_ns"],before["last_valid_ns"]);EXPECT_EQ(state()["worker_unusable"],true);EXPECT_EQ(state()["worker_valid"],false);}
TEST_F(C34LeaseMatrix,DuplicatePayloadRenewsReceiptLease){auto a=good();send(a);auto before=state();send(a);EXPECT_GT(state()["last_valid_ns"].get<int64_t>(),before["last_valid_ns"].get<int64_t>());EXPECT_EQ(state()["input_commit_ordinal"],0);}
TEST_F(C34LeaseMatrix,NoValidCapabilityNoWorkerValid){auto a=good();a.backend="other";send(a);EXPECT_EQ(state()["last_valid_ns"],0);EXPECT_EQ(state()["worker_valid"],false);EXPECT_EQ(state()["worker_unusable"],false);}
TEST_F(C34LeaseMatrix,FatalThenValidCannotRevive){auto a=good();send(a);auto before=state();auto b=a;b.fatal=true;send(b);send(a);EXPECT_EQ(state()["last_valid_ns"],before["last_valid_ns"]);EXPECT_EQ(state()["worker_valid"],false);EXPECT_EQ(state()["worker_unusable"],true);}
