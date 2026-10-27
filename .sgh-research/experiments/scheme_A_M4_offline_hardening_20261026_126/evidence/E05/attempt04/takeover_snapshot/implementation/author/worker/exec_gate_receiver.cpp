// Non-ROS exec receiver using the actual reviewed gate v2 and PipeReader.
// It never loads a solver and never publishes any control.
#include "w2_release_gate.hpp"
#include "w2_pipe_reader.hpp"
#include <atomic>
#include <chrono>
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dirent.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <thread>
#include <unistd.h>

static int64_t now_ns() {
  struct timespec ts{};
  ::clock_gettime(CLOCK_MONOTONIC, &ts);
  return int64_t(ts.tv_sec) * 1000000000LL + ts.tv_nsec;
}
static void ignore_signal(int) {}

int main(int argc, char **argv) {
  if (argc != 5) return 2;
  const int fd = std::atoi(argv[1]);
  const std::string mode = argv[2];
  const auto want_dev = std::strtoull(argv[3], nullptr, 10);
  const auto want_ino = std::strtoull(argv[4], nullptr, 10);
  struct stat st{};
  const int flags = ::fcntl(fd, F_GETFL);
  if (::fstat(fd, &st) || !S_ISFIFO(st.st_mode) ||
      static_cast<unsigned long long>(st.st_dev) != want_dev ||
      static_cast<unsigned long long>(st.st_ino) != want_ino ||
      flags < 0 || (flags & O_ACCMODE) != O_RDONLY) return 3;
  int channel_handles = 0;
  if (DIR *dir = ::opendir("/proc/self/fd")) {
    while (auto *entry = ::readdir(dir)) {
      char *end = nullptr;
      const auto candidate = std::strtol(entry->d_name, &end, 10);
      if (!end || *end || candidate < 0) continue;
      struct stat other{};
      if (::fstat(int(candidate), &other) == 0 && other.st_dev == st.st_dev &&
          other.st_ino == st.st_ino) ++channel_handles;
    }
    ::closedir(dir);
  }
  if (channel_handles != 1) return 4;
  struct sigaction sa{};
  sa.sa_handler = ignore_signal;
  sigemptyset(&sa.sa_mask);
  if (::sigaction(SIGUSR1, &sa, nullptr)) return 5;
  std::printf("{\"event\":\"ready\",\"pid\":%d,\"read_only\":true,"
              "\"channel_handles\":%d,\"device\":%llu,\"inode\":%llu}\n",
              int(::getpid()), channel_handles, want_dev, want_ino);
  std::fflush(stdout);
  std::atomic<bool> stop{false};
  std::thread stop_thread;
  if (mode == "stop") {
    stop_thread = std::thread([&] {
      std::this_thread::sleep_for(std::chrono::milliseconds(100));
      stop.store(true, std::memory_order_relaxed);
    });
  }
  w2_gate::Identity id{9, 5, 3, 0x1234};
  const int64_t budget = mode == "budget" ? 600000000LL : 2000000000LL;
  w2_gate::PipeReader reader(fd);
  w2_gate::Gate gate(&reader, id, budget);
  const auto started = now_ns();
  const auto outcome = gate.wait([&] { return stop.load(std::memory_order_relaxed); });
  const auto elapsed = now_ns() - started;
  if (stop_thread.joinable()) stop_thread.join();
  uint8_t expected[w2_gate::kFrameBytes];
  w2_gate::encode_release(expected, id);
  const bool frame_equal = outcome == w2_gate::Outcome::kReleased &&
      std::memcmp(expected, gate.frame_, w2_gate::kFrameBytes) == 0;
  std::printf("{\"event\":\"result\",\"outcome\":\"%s\",\"elapsed_ns\":%lld,"
              "\"budget_ns\":%lld,\"frame_equal\":%s,\"stop\":%s,"
              "\"actual_native_invoked\":false,\"component_only\":true}\n",
              w2_gate::outcome_name(outcome), static_cast<long long>(elapsed),
              static_cast<long long>(budget), frame_equal ? "true" : "false",
              stop.load(std::memory_order_relaxed) ? "true" : "false");
  std::fflush(stdout);
  ::close(fd);
  return 0;
}
