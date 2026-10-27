#include "v2_diagnostic_block.hpp"
#include <iostream>
#include <stdexcept>

int main() {
  unsigned checks = 0;
  auto check = [&](bool value) { ++checks; if (!value) throw std::runtime_error("V2 diagnostic block check failed"); };
  using v2_diagnostic::Block;
  Block disabled("none", 0, false, false, true);
  check(!disabled.enabled()); check(disabled.milliseconds() == 0);
  check(!disabled.take(0)); check(!disabled.take(1)); check(!disabled.take(100));
  Block once(v2_diagnostic::policy, 1700, true, true, false);
  check(once.enabled()); check(once.milliseconds() == 1700);
  check(!once.take(0)); check(once.take(1)); check(!once.take(1)); check(!once.take(2));
  Block fresh_run(v2_diagnostic::policy, 1700, true, true, false);
  check(!fresh_run.take(0)); check(fresh_run.take(2)); check(!fresh_run.take(3));
  auto reject = [&](const std::string &name, int ms, bool diagnostic, bool permission, bool execute) {
    bool caught = false;
    try { Block b(name, ms, diagnostic, permission, execute); } catch (const std::runtime_error &) { caught = true; }
    check(caught);
  };
  reject("unknown", 1700, true, true, false);
  reject("none", 1700, true, true, false);
  reject(v2_diagnostic::policy, 0, true, true, false);
  reject(v2_diagnostic::policy, 1699, true, true, false);
  reject(v2_diagnostic::policy, 1701, true, true, false);
  reject(v2_diagnostic::policy, 1700, false, true, false);
  reject(v2_diagnostic::policy, 1700, true, false, false);
  reject(v2_diagnostic::policy, 1700, true, true, true);
  std::cout << "checks=" << checks << " passed\n";
}
