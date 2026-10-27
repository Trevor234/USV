// Read-only review probes against the existing W2 headers.
// These print observations; a successful probe process is not a gate PASS.
#include "w2_release_gate.hpp"
#include "w2_pipe_reader.hpp"
#include <atomic>
#include <chrono>
#include <csignal>
#include <cstdio>
#include <cstring>
#include <sys/wait.h>
#include <type_traits>
#include <unistd.h>

using namespace w2_gate;
static int64_t now_ns() {
  return std::chrono::duration_cast<std::chrono::nanoseconds>(
      std::chrono::steady_clock::now().time_since_epoch()).count();
}
static Identity id() { return {7, 3, 2, 0xabcd}; }
static void no_op_signal(int) {}
static void reap(pid_t child) {
  int status = 0;
  while (::waitpid(child, &status, 0) < 0 && errno == EINTR) {}
}

class FullReader final : public Reader {
 public:
  FullReader(bool * stop, bool late) : stop_(stop), late_(late) {}
  long read_some(uint8_t * out, size_t n, int64_t timeout,
                 int64_t * elapsed) override {
    if (stop_) *stop_ = true;  // same thread: no data race in this probe
    uint8_t frame[kFrameBytes];
    encode_release(frame, id());
    std::memcpy(out, frame, n);
    *elapsed = late_ ? timeout + 1 : 1;
    return long(n);
  }
 private:
  bool * stop_;
  bool late_;
};

class TimeoutReader final : public Reader {
 public:
  long read_some(uint8_t *, size_t, int64_t, int64_t * elapsed) override {
    *elapsed = 0;
    return -1;  // exact return value used by the invalid-fd mutation
  }
};

int main() {
  {
    bool stop = false;
    FullReader reader(&stop, false);
    Gate gate(&reader, id(), 1000000);
    auto result = gate.wait(&stop);
    std::printf("{\"probe\":\"stop_during_full_read\",\"observed\":\"%s\","
                "\"stop_at_return\":%s,\"defect_reproduced\":%s}\n",
                outcome_name(result), stop ? "true" : "false",
                stop && result == Outcome::kReleased ? "true" : "false");
  }
  {
    FullReader reader(nullptr, true);
    Gate gate(&reader, id(), 1000000);
    auto result = gate.wait(nullptr);
    std::printf("{\"probe\":\"reader_reports_over_budget\",\"observed\":\"%s\","
                "\"defect_reproduced\":%s}\n", outcome_name(result),
                result == Outcome::kReleased ? "true" : "false");
  }
  {
    TimeoutReader reader;
    Gate gate(&reader, id(), 5000000000LL);
    const auto started = now_ns();
    auto result = gate.wait(nullptr);
    std::printf("{\"probe\":\"negative_return_is_immediate\",\"observed\":\"%s\","
                "\"elapsed_ns\":%lld}\n", outcome_name(result),
                static_cast<long long>(now_ns() - started));
  }
  std::printf("{\"probe\":\"atomic_pointer_compatibility\","
              "\"atomic_bool_pointer_converts_to_const_bool_pointer\":%s}\n",
              std::is_convertible<std::atomic<bool> *, const bool *>::value ? "true" : "false");

  struct sigaction sa{}, old{};
  sa.sa_handler = no_op_signal;
  sigemptyset(&sa.sa_mask);
  sa.sa_flags = 0;
  if (::sigaction(SIGUSR1, &sa, &old) != 0) return 2;
  uint8_t frame[kFrameBytes];
  encode_release(frame, id());

  {
    int fds[2];
    if (::pipe(fds) != 0) return 3;
    const auto parent = ::getpid();
    const auto child = ::fork();
    if (child < 0) return 4;
    if (child == 0) {
      ::close(fds[0]);
      ::usleep(100000);
      ::kill(parent, SIGUSR1);
      ::usleep(100000);
      const auto n = ::write(fds[1], frame, kFrameBytes);
      ::close(fds[1]);
      ::_exit(n == long(kFrameBytes) ? 0 : 5);
    }
    ::close(fds[1]);
    PipeReader reader(fds[0]);
    uint8_t out[kFrameBytes]{};
    int64_t elapsed = 0;
    const auto started = now_ns();
    auto n = reader.read_some(out, kFrameBytes, 1000000000LL, &elapsed);
    const auto actual = now_ns() - started;
    reap(child);
    ::close(fds[0]);
    std::printf("{\"probe\":\"eintr_elapsed_accounting\",\"read_bytes\":%ld,"
                "\"reported_ns\":%lld,\"actual_ns\":%lld,\"defect_reproduced\":%s}\n",
                n, static_cast<long long>(elapsed), static_cast<long long>(actual),
                actual - elapsed > 50000000 ? "true" : "false");
  }
  {
    int fds[2];
    if (::pipe(fds) != 0) return 6;
    const auto parent = ::getpid();
    const auto child = ::fork();
    if (child < 0) return 7;
    if (child == 0) {
      ::close(fds[0]);
      ::usleep(200000);
      ::kill(parent, SIGUSR1);
      ::usleep(200000);
      const auto a = ::write(fds[1], frame, 22);
      ::usleep(350000);
      const auto b = ::write(fds[1], frame + 22, 22);
      ::close(fds[1]);
      ::_exit(a == 22 && b == 22 ? 0 : 8);
    }
    ::close(fds[1]);
    PipeReader reader(fds[0]);
    constexpr int64_t budget = 600000000LL;
    Gate gate(&reader, id(), budget);
    const auto started = now_ns();
    auto result = gate.wait(nullptr);
    const auto actual = now_ns() - started;
    reap(child);
    ::close(fds[0]);
    std::printf("{\"probe\":\"eintr_partial_frame_total_budget\",\"observed\":\"%s\","
                "\"budget_ns\":%lld,\"actual_ns\":%lld,\"defect_reproduced\":%s}\n",
                outcome_name(result), static_cast<long long>(budget),
                static_cast<long long>(actual),
                result == Outcome::kReleased && actual > budget + 50000000 ? "true" : "false");
  }
  ::sigaction(SIGUSR1, &old, nullptr);
  return 0;
}
