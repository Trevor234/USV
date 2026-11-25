// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT
#include "p1_sys_utils.hpp"

#include <cerrno>
#include <cctype>
#include <ctime>
#include <fstream>
#include <iterator>
#include <stdexcept>

#include <openssl/sha.h>

namespace p1 {
namespace {

constexpr std::int64_t kNanosecondsPerSecond = 1'000'000'000;

}  // namespace

std::int64_t monotonic_ns() {
  timespec time{};
  if (clock_gettime(CLOCK_MONOTONIC, &time) != 0) {
    throw std::runtime_error("CLOCK_MONOTONIC failed");
  }
  return std::int64_t(time.tv_sec) * kNanosecondsPerSecond + time.tv_nsec;
}

void sleep_until_monotonic(std::int64_t ns) {
  const timespec time{ns / kNanosecondsPerSecond, ns % kNanosecondsPerSecond};
  int result;
  do {
    result = clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &time, nullptr);
  } while (result == EINTR);
  if (result != 0) throw std::runtime_error("absolute monotonic sleep failed");
}

std::string read_text(const std::string & path) {
  std::ifstream file(path);
  if (!file) throw std::runtime_error("read failed: " + path);
  return {std::istreambuf_iterator<char>(file), {}};
}

std::string digest(const std::string & text) {
  unsigned char hash[SHA256_DIGEST_LENGTH];
  if (!SHA256(reinterpret_cast<const unsigned char *>(text.data()), text.size(), hash)) {
    throw std::runtime_error("SHA256 failed");
  }
  constexpr char hex[] = "0123456789abcdef";
  std::string result(2 * SHA256_DIGEST_LENGTH, '\0');
  for (std::size_t i = 0; i < SHA256_DIGEST_LENGTH; ++i) {
    result[2 * i] = hex[hash[i] >> 4];
    result[2 * i + 1] = hex[hash[i] & 0x0f];
  }
  return result;
}

std::string boot_id() {
  auto text = read_text("/proc/sys/kernel/random/boot_id");
  while (!text.empty() && std::isspace(static_cast<unsigned char>(text.back()))) {
    text.pop_back();
  }
  return text;
}

}  // namespace p1
