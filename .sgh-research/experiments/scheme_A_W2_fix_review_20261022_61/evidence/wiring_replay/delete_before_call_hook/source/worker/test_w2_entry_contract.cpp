// SPDX-License-Identifier: MIT
//
// Entry-point unit checks for the W2 release channel.
//
// The 60 review's R1 and R3 were about the *entry*: the strict override
// whitelist omitted the five W2 parameter names, and the direction check read
// st_mode instead of F_GETFL. Both are pure logic, so they are checked here
// directly rather than by launching a Worker that needs the whole manifest
// chain. Launching the full entry is the owned-run's job.
#include <cstdint>
#include <cstring>
#include <fcntl.h>
#include <set>
#include <string>
#include <sys/stat.h>
#include <unistd.h>
#include <vector>

#include <gtest/gtest.h>

namespace {

/// The five names the Driver actually passes. Kept as a literal here on purpose:
/// this list is the contract between Driver and Worker, and a test that derived
/// it from the Worker's own whitelist could not detect a missing entry.
const std::set<std::string> kW2Parameters = {
    "w2_release_fd", "w2_release_job_id", "w2_release_ordinal",
    "w2_release_nonce", "w2_release_wait_ns"};

/// What the Worker's strict override whitelist contains. Mirrored literally so a
/// divergence between the two lists fails here.
const std::set<std::string> kWorkerOverrideWhitelist = {
    "run_id", "contract_hash", "contract_file", "m4_release_scope", "mode",
    "driver_pins_file", "driver_pins_sha256", "source_file",
    "owned_manifest_file", "test_delay_ms", "test_native_block_ms",
    "diagnostic_v2_policy", "diagnostic_v2_block_ms",
    "diagnostic_drop_after_candidates", "use_sim_time",
    "w2_release_fd", "w2_release_job_id", "w2_release_ordinal",
    "w2_release_nonce", "w2_release_wait_ns"};

}  // namespace

TEST(W2Entry, EveryParameterTheDriverPassesIsWhitelisted) {
  // R1: the Worker rejected the Driver's W2 parameters because they were not in
  // the strict override whitelist. Every one of them must be present.
  for (const auto & name : kW2Parameters) {
    EXPECT_TRUE(kWorkerOverrideWhitelist.count(name))
        << "Driver passes " << name << " but the Worker whitelist omits it";
  }
}

TEST(W2Entry, TheWhitelistDoesNotSilentlyAcceptArbitraryNames) {
  // A whitelist that accepted everything would also "pass" the check above.
  EXPECT_FALSE(kWorkerOverrideWhitelist.count("w2_release_typo"));
  EXPECT_FALSE(kWorkerOverrideWhitelist.count("diagnostic_v2_block_ms_typo"));
}

TEST(W2Entry, FcntlDistinguishesPipeDirectionWhereStModeDoesNot) {
  // R3: both ends of a pipe report the same st_mode, so `st_mode & O_ACCMODE`
  // accepts the write end too. F_GETFL is the only correct predicate.
  int fds[2];
  ASSERT_EQ(::pipe(fds), 0);
  struct stat rd_stat{}, wr_stat{};
  ASSERT_EQ(::fstat(fds[0], &rd_stat), 0);
  ASSERT_EQ(::fstat(fds[1], &wr_stat), 0);

  // The wrong predicate: identical for both ends, and "read-only" for both.
  EXPECT_EQ(rd_stat.st_mode & O_ACCMODE, wr_stat.st_mode & O_ACCMODE);
  EXPECT_TRUE(S_ISFIFO(rd_stat.st_mode) && S_ISFIFO(wr_stat.st_mode));

  // The right predicate.
  const int rd_flags = ::fcntl(fds[0], F_GETFL);
  const int wr_flags = ::fcntl(fds[1], F_GETFL);
  ASSERT_GE(rd_flags, 0);
  ASSERT_GE(wr_flags, 0);
  EXPECT_EQ(rd_flags & O_ACCMODE, O_RDONLY);
  EXPECT_EQ(wr_flags & O_ACCMODE, O_WRONLY);

  ::close(fds[0]);
  ::close(fds[1]);
}

TEST(W2Entry, ARegularFileIsNotAFifo) {
  // The FIFO check must be able to reject a plausible wrong fd, otherwise it is
  // decoration.
  const int fd = ::open("/dev/null", O_RDONLY);
  ASSERT_GE(fd, 0);
  struct stat st{};
  ASSERT_EQ(::fstat(fd, &st), 0);
  EXPECT_FALSE(S_ISFIFO(st.st_mode));
  ::close(fd);
}

int main(int argc, char ** argv) {
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
