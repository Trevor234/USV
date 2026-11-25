// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT
#pragma once

#include <cstdint>
#include <string>

namespace p1 {

std::int64_t monotonic_ns();
void sleep_until_monotonic(std::int64_t ns);
std::string read_text(const std::string & path);
std::string digest(const std::string & text);
std::string boot_id();

}  // namespace p1
