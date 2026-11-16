#pragma once
#include <cstdint>
#include <stdexcept>
#include <string>

namespace p1 {
// Diagnostic only. The caller owns the finite, cancellation-aware wait.
class PreparationBarrier {
 public:
  PreparationBarrier(int64_t milliseconds, const std::string & mode,
                     bool fault_enabled, uint64_t ordinal = 3)
      : milliseconds_(milliseconds), ordinal_(ordinal) {
    // 准入：no_output 诊断，或受控仿真且合同显式启用了故障注入。
    // execute/shadow 一律拒绝 —— 诊断屏障不得进入物理输出路径。
    const bool admitted = mode == "no_output" ||
                          (mode == "controlled_sim" && fault_enabled);
    if (milliseconds < 0 || milliseconds > 3000 ||
        (milliseconds && !admitted))
      throw std::runtime_error("preparation barrier requires bounded no_output fault diagnostic");
  }
  bool take() { return milliseconds_ > 0 && ++taken_ == ordinal_; }
  int64_t milliseconds() const { return milliseconds_; }
 private:
  int64_t milliseconds_; uint64_t taken_ = 0; uint64_t ordinal_ = 3;
};
}
