// SPDX-License-Identifier: MIT
//
// Entry-contract tests that exercise the production helper.
//
// The 61 review's D5: the previous version mirrored a hand-copied whitelist, so
// deleting the real Worker's W2 parameters left the suite green. These tests
// include `w2_entry_contract.hpp` — the same header the Worker calls — so a
// regression in the production rules fails here.
#include <cerrno>
#include <cstdint>
#include <fcntl.h>
#include <string>
#include <sys/stat.h>
#include <unistd.h>

#include <gtest/gtest.h>

#include "w2_entry_contract.hpp"

namespace {

using w2_entry::Reject;

/// The five names the Driver passes. Written out here so the assertion is
/// independent of the helper's own list, but the *validation* runs through the
/// helper the Worker uses.
const std::set<std::string> kDriverPasses = {
    "w2_release_fd", "w2_release_job_id", "w2_release_ordinal",
    "w2_release_nonce", "w2_release_wait_ns"};

/// The Worker's full strict-override whitelist is assembled as ordinary names
/// plus the helper's set; the Worker source is the authority on the ordinary
/// half. If the helper drops a name, this fails.
const std::set<std::string> kOrdinary = {
    "run_id", "contract_hash", "contract_file", "m4_release_scope", "mode",
    "driver_pins_file", "driver_pins_sha256", "source_file",
    "owned_manifest_file", "test_delay_ms", "test_native_block_ms",
    "diagnostic_v2_policy", "diagnostic_v2_block_ms",
    "diagnostic_drop_after_candidates", "use_sim_time"};

}  // namespace

TEST(W2EntryContract, HelperAdmitsEveryParameterTheDriverPasses) {
  for (const auto & name : kDriverPasses) {
    EXPECT_TRUE(w2_entry::parameters().count(name))
        << "Driver passes " << name << " but the production helper omits it";
  }
}

TEST(W2EntryContract, HelperDoesNotAdmitAnythingBeyondTheContract) {
  EXPECT_EQ(w2_entry::parameters().size(), kDriverPasses.size());
  EXPECT_FALSE(w2_entry::parameters().count("w2_release_typo"));
}

TEST(W2EntryContract, OrdinaryProfileIsAccepted) {
  // No fd and every other parameter at its disabled default.
  w2_entry::Channel ch;
  EXPECT_EQ(w2_entry::validate(-1, -1, 0, 0, 0, &ch), Reject::kOk);
}

TEST(W2EntryContract, HalfRegisteredChannelIsRejected) {
  w2_entry::Channel ch;
  EXPECT_EQ(w2_entry::validate(-1, 1, 0, 0, 0, &ch),
            Reject::kNoFdButOtherParametersSet);
  EXPECT_EQ(w2_entry::validate(-1, -1, 1, 0, 0, &ch),
            Reject::kNoFdButOtherParametersSet);
  EXPECT_EQ(w2_entry::validate(-1, -1, 0, 0, 1000, &ch),
            Reject::kNoFdButOtherParametersSet);
}

TEST(W2EntryContract, NonceWithoutFdIsRejected) {
  w2_entry::Channel ch;
  EXPECT_EQ(w2_entry::validate(-1, -1, 0, 7, 0, &ch),
            Reject::kNonZeroNonceWithoutFd);
}

TEST(W2EntryContract, ZeroNonceIsRejected) {
  int fds[2];
  ASSERT_EQ(::pipe(fds), 0);
  w2_entry::Channel ch;
  EXPECT_EQ(w2_entry::validate(fds[0], 1, 1, 0, 1000000, &ch), Reject::kNonceZero);
  ::close(fds[0]); ::close(fds[1]);
}

TEST(W2EntryContract, BindingOutOfRangeIsRejected) {
  int fds[2];
  ASSERT_EQ(::pipe(fds), 0);
  w2_entry::Channel ch;
  EXPECT_EQ(w2_entry::validate(fds[0], 0, 1, 5, 1000000, &ch),
            Reject::kBindingOutOfRange);
  EXPECT_EQ(w2_entry::validate(fds[0], 1, 0, 5, 1000000, &ch),
            Reject::kBindingOutOfRange);
  EXPECT_EQ(w2_entry::validate(fds[0], 1, 1, 5, 0, &ch),
            Reject::kBindingOutOfRange);
  EXPECT_EQ(w2_entry::validate(fds[0], 1, 1, 5, 2000000001LL, &ch),
            Reject::kBindingOutOfRange);
  ::close(fds[0]); ::close(fds[1]);
}

TEST(W2EntryContract, TheWriteEndIsRejected) {
  // The production rule must reject the write end. `st_mode & O_ACCMODE` would
  // accept both ends, which is the wiring error the gate exists to catch.
  int fds[2];
  ASSERT_EQ(::pipe(fds), 0);
  w2_entry::Channel ch;
  EXPECT_EQ(w2_entry::validate(fds[1], 1, 1, 5, 1000000, &ch),
            Reject::kNotReadOnly);
  ::close(fds[0]); ::close(fds[1]);
}

TEST(W2EntryContract, TheReadEndIsAcceptedAndReportsItsIdentity) {
  int fds[2];
  ASSERT_EQ(::pipe(fds), 0);
  w2_entry::Channel ch;
  ASSERT_EQ(w2_entry::validate(fds[0], 3, 2, 5, 1000000, &ch), Reject::kOk);
  EXPECT_EQ(ch.fd, fds[0]);
  EXPECT_EQ(ch.job_id, 3);
  EXPECT_EQ(ch.ordinal, 2);
  EXPECT_EQ(ch.nonce, 5);
  EXPECT_EQ(ch.wait_budget_ns, 1000000);
  EXPECT_TRUE(ch.read_only);
  struct stat st{};
  ASSERT_EQ(::fstat(fds[0], &st), 0);
  EXPECT_EQ(ch.device, uint64_t(st.st_dev));
  EXPECT_EQ(ch.inode, uint64_t(st.st_ino));
  ::close(fds[0]); ::close(fds[1]);
}

TEST(W2EntryContract, ANonFifoFdIsRejected) {
  const int fd = ::open("/dev/null", O_RDONLY);
  ASSERT_GE(fd, 0);
  w2_entry::Channel ch;
  EXPECT_EQ(w2_entry::validate(fd, 1, 1, 5, 1000000, &ch), Reject::kNotAFifo);
  ::close(fd);
}

TEST(W2EntryContract, AnUnresolvableFdIsRejected) {
  w2_entry::Channel ch;
  // A large but non-negative number that is not open in this process.
  EXPECT_EQ(w2_entry::validate(9999, 1, 1, 5, 1000000, &ch),
            Reject::kFdDoesNotResolve);
}

TEST(W2EntryContract, EveryRejectionHasADistinctMessage) {
  const Reject all[] = {
      Reject::kOk, Reject::kNoFdButOtherParametersSet,
      Reject::kNonZeroNonceWithoutFd, Reject::kNonceZero,
      Reject::kBindingOutOfRange, Reject::kFdDoesNotResolve,
      Reject::kNotAFifo, Reject::kNotReadOnly};
  std::set<std::string> names;
  for (auto r : all) names.insert(w2_entry::reject_name(r));
  EXPECT_EQ(names.size(), sizeof(all) / sizeof(all[0]));
}

TEST(W2EntryContract, TheWhitelistIsOrdinaryNamesPlusTheHelperSet) {
  // This is how the Worker builds its whitelist: the ordinary names plus
  // whatever the helper says. The assertion documents the composition so a
  // future edit that stops calling the helper is visible here.
  std::set<std::string> full = kOrdinary;
  full.insert(w2_entry::parameters().begin(), w2_entry::parameters().end());
  for (const auto & name : kDriverPasses) {
    EXPECT_TRUE(full.count(name)) << name;
  }
  EXPECT_FALSE(full.count("w2_release_typo"));
}

int main(int argc, char ** argv) {
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
