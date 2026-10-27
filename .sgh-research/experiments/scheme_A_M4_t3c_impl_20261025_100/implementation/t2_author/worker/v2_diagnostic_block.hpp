// Diagnostic work-thread barrier before the native solver call. No native-hang claim.
#pragma once
#include <cstdint>
#include <stdexcept>
#include <string>

namespace v2_diagnostic {
inline constexpr const char *policy = "pre_native_once_after_completed_v1";
class Block {
 public:
  Block(const std::string &name, int milliseconds, bool diagnostic, bool permission, bool execute)
      : milliseconds_(milliseconds), enabled_(name == policy) {
    if (name != "none" && name != policy) throw std::runtime_error("V2_unknown_policy");
    if (!enabled_ && milliseconds != 0) throw std::runtime_error("V2_disabled_duration");
    if (enabled_ && (!diagnostic || !permission || execute || milliseconds != 1700))
      throw std::runtime_error("V2_requires_explicit_nonexecuting_diagnostic_1700ms");
  }
  bool take(uint64_t completed_jobs) {
    if (!enabled_ || taken_ || completed_jobs < 1) return false;
    taken_ = true;
    return true;
  }
  int milliseconds() const { return milliseconds_; }
  bool enabled() const { return enabled_; }
 private:
  int milliseconds_;
  bool enabled_, taken_ = false;
};
}
