#pragma once
#include <cstdint>
#include <stdexcept>
#include <string>

namespace p1 {
// Diagnostic only. The caller owns the finite, cancellation-aware wait.
class PreparationBarrier {
 public:
  PreparationBarrier(int64_t milliseconds, const std::string & mode, bool fault_enabled)
      : milliseconds_(milliseconds) {
    if (milliseconds < 0 || milliseconds > 3000 ||
        (milliseconds && (mode != "no_output" || !fault_enabled)))
      throw std::runtime_error("preparation barrier requires bounded no_output fault diagnostic");
  }
  bool take() { return milliseconds_ > 0 && ++taken_ == 3; }
  int64_t milliseconds() const { return milliseconds_; }
 private:
  int64_t milliseconds_; uint64_t taken_ = 0;
};
}
