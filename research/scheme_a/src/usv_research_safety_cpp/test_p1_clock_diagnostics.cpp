// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT
//
// 诊断仪表的确定性回归。它只断言**消费者可见的证据错误**：
//   * 饱和缓冲必须停住并计 dropped，绝不循环覆盖（尾部丢失不能被当成完整证据）；
//   * 已存在的文件/不可写父目录必须显式失败且不改旧字节；
//   * 正常收尾与析构兜底只能产生一份 summary；
//   * 空路径分支不产生 trace、不改变默认执行。
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <string>
#include <vector>

#include <gtest/gtest.h>

#include "p1_clock_diagnostics.hpp"

namespace
{

std::string read_all(const std::string & path)
{
  std::ifstream input(path);
  return std::string(std::istreambuf_iterator<char>(input), {});
}

std::vector<nlohmann::json> read_lines(const std::string & path)
{
  std::vector<nlohmann::json> rows;
  std::ifstream input(path);
  std::string line;
  while (std::getline(input, line)) {
    if (line.empty()) continue;
    rows.push_back(nlohmann::json::parse(line));
  }
  return rows;
}

std::string temp_dir()
{
  char pattern[] = "/tmp/p1_clock_diag_XXXXXX";
  char * made = ::mkdtemp(pattern);
  return made == nullptr ? std::string("/tmp") : std::string(made);
}

}  // namespace

TEST(P1ClockDiagnostics, SaturatedBufferKeepsThePrefixAndCountsTheDrop)
{
  p1_clock_diag::BoundedTrace<4> trace;
  for (int i = 0; i < 6; ++i) {
    trace.append(p1_clock_diag::Record(p1_clock_diag::kPumpBegin,
                                       p1_clock_diag::kPlantExecutor,
                                       std::int64_t(i + 1) * 1000)
                     .sim(std::int64_t(i) * 50000000)
                     .get());
  }
  EXPECT_EQ(trace.stored(), 4u);
  EXPECT_EQ(trace.attempted(), 6u);
  EXPECT_EQ(trace.dropped(), 2u);
  EXPECT_FALSE(trace.complete());
  // 保留的是第 1..4 条（绝不覆盖），seq 由缓冲自己按流内自增编号。
  for (std::uint32_t i = 0; i < 4; ++i) {
    EXPECT_EQ(trace.data()[i].seq, i + 1);
    EXPECT_EQ(trace.data()[i].at_ns, std::int64_t(i + 1) * 1000);
  }
}

TEST(P1ClockDiagnostics, SummaryIsWrittenOnceAndReportsIncompleteness)
{
  const std::string dir = temp_dir();
  const std::string path = dir + "/plant.clock-diagnostics.jsonl";
  p1_clock_diag::BoundedTrace<4> trace;
  for (int i = 0; i < 6; ++i) {
    trace.append(p1_clock_diag::Record(p1_clock_diag::kPumpEnd,
                                       p1_clock_diag::kPlantExecutor,
                                       std::int64_t(i + 1) * 1000)
                     .exit(p1_clock_diag::kExitIdleNotDue)
                     .get());
  }
  {
    auto writer = p1_clock_diag::Diagnostics::create(path, {{"producer", "p1_x86_plant"},
                                                            {"pid", 1},
                                                            {"run_id", "run"},
                                                            {"boot_id", "boot"},
                                                            {"host_boot_id", "host"}});
    writer->add_stream("plant_executor", trace);
    EXPECT_TRUE(writer->flush());
    EXPECT_TRUE(writer->flush());   // 幂等：不重复写 summary
    EXPECT_TRUE(writer->flush_ok());
  }
  const auto rows = read_lines(path);
  ASSERT_GE(rows.size(), 3u);
  EXPECT_EQ(rows.front()["type"], "clock_diagnostics_header");
  EXPECT_EQ(rows.back()["type"], "clock_diagnostics_summary");
  EXPECT_FALSE(rows.back()["complete"].get<bool>());
  EXPECT_EQ(rows.back()["dropped"].get<std::uint64_t>(), 2u);
  EXPECT_EQ(rows.back()["stored"].get<std::uint64_t>(), 4u);
  int summaries = 0;
  for (const auto & row : rows) {
    if (row["type"] == "clock_diagnostics_summary") ++summaries;
  }
  EXPECT_EQ(summaries, 1);
  ::remove(path.c_str());
  ::rmdir(dir.c_str());
}

TEST(P1ClockDiagnostics, ExistingFileIsRefusedAndBytesAreUntouched)
{
  const std::string dir = temp_dir();
  const std::string path = dir + "/plant.clock-diagnostics.jsonl";
  const std::string original = "{\"type\":\"previous-run\"}\n";
  {
    std::ofstream out(path);
    out << original;
  }
  EXPECT_THROW(p1_clock_diag::Diagnostics::create(path, {{"producer", "p1_x86_plant"}}),
               std::runtime_error);
  EXPECT_EQ(read_all(path), original);
  ::remove(path.c_str());
  ::rmdir(dir.c_str());
}

TEST(P1ClockDiagnostics, MissingParentDirectoryFailsLoudly)
{
  EXPECT_THROW(p1_clock_diag::Diagnostics::create(
                   "/tmp/p1_clock_diag_absent_parent/plant.jsonl",
                   {{"producer", "p1_x86_plant"}}),
               std::runtime_error);
}

TEST(P1ClockDiagnostics, WriteFailureNeverReportsSuccess)
{
  const std::string dir = temp_dir();
  const std::string path = dir + "/plant.clock-diagnostics.jsonl";
  p1_clock_diag::BoundedTrace<8> trace;
  auto writer = p1_clock_diag::Diagnostics::create(path, {{"producer", "p1_x86_plant"}});
  writer->add_stream("plant_executor", trace);
  // 人为破坏底层流：关闭 fd 后再 flush 必须给出 false，绝不冒充成功。
  const int fd = writer->flushed() ? -1 : fileno(writer->file_for_test());
  if (fd >= 0) ::close(fd);
  EXPECT_FALSE(writer->flush());
  EXPECT_FALSE(writer->flush_ok());
  ::remove(path.c_str());
  ::rmdir(dir.c_str());
}

TEST(P1ClockDiagnostics, MappedRowsCarryTheirOwnOrigin)
{
  const std::string dir = temp_dir();
  const std::string path = dir + "/plant.clock-diagnostics.jsonl";
  p1_clock_diag::BoundedTrace<8> trace;
  // resync 合法改变 origin：两行必须各自带本行生效的 origin。
  trace.append(p1_clock_diag::Record(p1_clock_diag::kClockPublishBegin,
                                     p1_clock_diag::kPlantExecutor, 1000)
                   .sim(50000000)
                   .mapped(100000050000000LL, 100000000000000LL)
                   .get());
  trace.append(p1_clock_diag::Record(p1_clock_diag::kClockPublishBegin,
                                     p1_clock_diag::kPlantExecutor, 2000)
                   .sim(100000000)
                   .mapped(200000100000000LL, 200000000000000LL)
                   .get());
  {
    auto writer = p1_clock_diag::Diagnostics::create(path, {{"producer", "p1_x86_plant"}});
    writer->add_stream("plant_executor", trace);
    EXPECT_TRUE(writer->flush());
  }
  const auto rows = read_lines(path);
  std::size_t checked = 0;
  for (const auto & row : rows) {
    if (row["type"] != "clock_diagnostics") continue;
    ASSERT_TRUE(row.contains("origin_ns"));
    EXPECT_EQ(row["mapped_steady_ns"].get<std::int64_t>(),
              row["origin_ns"].get<std::int64_t>() + row["sim_ns"].get<std::int64_t>());
    ++checked;
  }
  EXPECT_EQ(checked, 2u);
  ::remove(path.c_str());
  ::rmdir(dir.c_str());
}

TEST(P1ClockDiagnostics, LongReasonIsMarkedTruncatedInsteadOfSilentlyCut)
{
  const std::string dir = temp_dir();
  const std::string path = dir + "/plant.clock-diagnostics.jsonl";
  p1_clock_diag::BoundedTrace<4> trace;
  const std::string long_reason(300, 'x');
  trace.append(p1_clock_diag::Record(p1_clock_diag::kReceiveEnd,
                                     p1_clock_diag::kPlantExecutor, 1)
                   .text(long_reason)
                   .get());
  {
    auto writer = p1_clock_diag::Diagnostics::create(path, {{"producer", "p1_x86_plant"}});
    writer->add_stream("plant_executor", trace);
    EXPECT_TRUE(writer->flush());
  }
  const auto rows = read_lines(path);
  const nlohmann::json * record = nullptr;
  for (const auto & row : rows) {
    if (row["type"] == "clock_diagnostics") record = &row;
  }
  ASSERT_NE(record, nullptr);
  ASSERT_TRUE(record->contains("reason_truncated"));
  EXPECT_TRUE((*record)["reason_truncated"].get<bool>());
  EXPECT_LT(std::string((*record)["reason"]).size(), long_reason.size());
  ::remove(path.c_str());
  ::rmdir(dir.c_str());
}

int main(int argc, char ** argv)
{
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
