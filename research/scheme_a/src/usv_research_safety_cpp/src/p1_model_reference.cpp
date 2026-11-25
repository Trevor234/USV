// SPDX-License-Identifier: MIT
//
// model_reference_binding_v1.cpp — 有限模型表的实现。
//
// 自包含 SHA-256；R01 的冻结计划解析使用项目已有的 nlohmann/json 头，
// 不链接 OpenSSL、Eigen、acados 或 ROS。
// 它不是密码学产品代码，只是把 30 个 binary64 与表结构变成稳定摘要。

#include "p1_model_reference.hpp"
#include <nlohmann/json.hpp>

#include <cmath>
#include <cstring>
#include <limits>

namespace model_reference {
namespace {

// ---- 最小 SHA-256（FIPS 180-4） ----------------------------------------
struct Sha256 {
  std::uint32_t h[8] = {0x6a09e667u, 0xbb67ae85u, 0x3c6ef372u, 0xa54ff53au,
                        0x510e527fu, 0x9b05688cu, 0x1f83d9abu, 0x5be0cd19u};
  std::uint64_t total = 0;
  unsigned char buf[64]{};
  std::size_t used = 0;

  static std::uint32_t rotr(std::uint32_t x, int n) { return (x >> n) | (x << (32 - n)); }

  void block(const unsigned char *p) {
    static const std::uint32_t k[64] = {
        0x428a2f98u, 0x71374491u, 0xb5c0fbcfu, 0xe9b5dba5u, 0x3956c25bu, 0x59f111f1u,
        0x923f82a4u, 0xab1c5ed5u, 0xd807aa98u, 0x12835b01u, 0x243185beu, 0x550c7dc3u,
        0x72be5d74u, 0x80deb1feu, 0x9bdc06a7u, 0xc19bf174u, 0xe49b69c1u, 0xefbe4786u,
        0x0fc19dc6u, 0x240ca1ccu, 0x2de92c6fu, 0x4a7484aau, 0x5cb0a9dcu, 0x76f988dau,
        0x983e5152u, 0xa831c66du, 0xb00327c8u, 0xbf597fc7u, 0xc6e00bf3u, 0xd5a79147u,
        0x06ca6351u, 0x14292967u, 0x27b70a85u, 0x2e1b2138u, 0x4d2c6dfcu, 0x53380d13u,
        0x650a7354u, 0x766a0abbu, 0x81c2c92eu, 0x92722c85u, 0xa2bfe8a1u, 0xa81a664bu,
        0xc24b8b70u, 0xc76c51a3u, 0xd192e819u, 0xd6990624u, 0xf40e3585u, 0x106aa070u,
        0x19a4c116u, 0x1e376c08u, 0x2748774cu, 0x34b0bcb5u, 0x391c0cb3u, 0x4ed8aa4au,
        0x5b9cca4fu, 0x682e6ff3u, 0x748f82eeu, 0x78a5636fu, 0x84c87814u, 0x8cc70208u,
        0x90befffau, 0xa4506cebu, 0xbef9a3f7u, 0xc67178f2u};

    std::uint32_t w[64];
    for (int i = 0; i < 16; ++i)
      w[i] = (std::uint32_t(p[4 * i]) << 24) | (std::uint32_t(p[4 * i + 1]) << 16) |
             (std::uint32_t(p[4 * i + 2]) << 8) | std::uint32_t(p[4 * i + 3]);
    for (int i = 16; i < 64; ++i) {
      std::uint32_t s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >> 3);
      std::uint32_t s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >> 10);
      w[i] = w[i - 16] + s0 + w[i - 7] + s1;
    }
    std::uint32_t a = h[0], b = h[1], c = h[2], d = h[3];
    std::uint32_t e = h[4], f = h[5], g = h[6], hh = h[7];
    for (int i = 0; i < 64; ++i) {
      std::uint32_t S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
      std::uint32_t ch = (e & f) ^ (~e & g);
      std::uint32_t t1 = hh + S1 + ch + k[i] + w[i];
      std::uint32_t S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
      std::uint32_t mj = (a & b) ^ (a & c) ^ (b & c);
      std::uint32_t t2 = S0 + mj;
      hh = g; g = f; f = e; e = d + t1; d = c; c = b; b = a; a = t1 + t2;
    }
    h[0] += a; h[1] += b; h[2] += c; h[3] += d;
    h[4] += e; h[5] += f; h[6] += g; h[7] += hh;
  }

  void update(const unsigned char *data, std::size_t n) {
    total += n;
    while (n > 0) {
      std::size_t take = 64 - used;
      if (take > n) take = n;
      std::memcpy(buf + used, data, take);
      used += take;
      data += take;
      n -= take;
      if (used == 64) { block(buf); used = 0; }
    }
  }

  Digest finish() {
    std::uint64_t bits = total * 8;
    unsigned char pad = 0x80;
    update(&pad, 1);
    unsigned char zero = 0;
    while (used != 56) update(&zero, 1);
    unsigned char len[8];
    for (int i = 0; i < 8; ++i) len[i] = static_cast<unsigned char>(bits >> (56 - 8 * i));
    // update() 会改 total，但 finish 只用 bits，已保存
    update(len, 8);
    char out[65];
    for (int i = 0; i < 8; ++i)
      std::snprintf(out + 8 * i, 9, "%08x", h[i]);
    return Digest(out, 64);
  }
};

void append_be64(Sha256 &s, std::uint64_t v) {
  unsigned char b[8];
  for (int i = 0; i < 8; ++i) b[i] = static_cast<unsigned char>(v >> (56 - 8 * i));
  s.update(b, 8);
}

void append_be_double(Sha256 &s, double v) {
  std::uint64_t bits;
  std::memcpy(&bits, &v, sizeof(bits));
  append_be64(s, bits);
}

}  // namespace

bool Registry::all_finite(const Content &c) {
  for (double v : c)
    if (!std::isfinite(v)) return false;
  return true;
}

bool Registry::content_equal(const Content &a, const Content &b) const {
  // 位比较，不用 ==（避免 -0.0 == 0.0 把不同位模式当成相同内容）
  return std::memcmp(a.data(), b.data(), sizeof(double) * kContentSize) == 0;
}

bool Registry::is_registered(std::uint64_t generation) const {
  return find(generation) != nullptr;
}

const Entry *Registry::find(std::uint64_t generation) const {
  if (generation == 0) return nullptr;
  for (std::size_t i = 0; i < count_; ++i)
    if (entries_[i].generation == generation) return &entries_[i];
  return nullptr;
}

bool Registry::register_generation(std::uint64_t generation, const Content &content,
                                   std::uint64_t first_target_tick,
                                   std::uint64_t last_target_tick) {
  if (frozen_) return false;                   // E06：冻结后一律拒绝
  if (generation == 0) return false;           // 零代拒绝
  if (!all_finite(content)) return false;      // 非 finite 拒绝
  if (first_target_tick == 0) return false;    // target 0 不属于任何 Job 计划
  if (!(last_target_tick == 0 || last_target_tick >= first_target_tick)) return false;

  // E06：区间不得重叠（重叠会让 resolve 有歧义）
  for (std::size_t i = 0; i < count_; ++i)
    if (entries_[i].generation != generation &&
        ranges_overlap(first_target_tick, last_target_tick,
                       entries_[i].first_target_tick, entries_[i].last_target_tick))
      return false;

  const Entry *existing = find(generation);
  if (existing) {
    // 一代一内容：同代换内容拒绝；同内容重复登记幂等
    return content_equal(existing->content, content) &&
           existing->first_target_tick == first_target_tick &&
           existing->last_target_tick == last_target_tick;
  }
  if (count_ >= kMaxEntries) return false;     // 表有界

  Entry &e = entries_[count_++];
  e.generation = generation;
  e.content = content;
  e.first_target_tick = first_target_tick;
  e.last_target_tick = last_target_tick;
  return true;
}

Selection Registry::resolve(const Grid &table_grid, const Grid &query_grid,
                            std::uint64_t target_tick,
                            const Options &opts) const {
  Selection s;
  if (!opts.model_switch_enabled) {
    s.reason = "model_switch_disabled";
    return s;
  }
  if (target_tick == 0) {
    // 计划层面的拒绝，不是启动错误：首个模型来自构造初始化。
    s.reason = "no_job_at_target_zero";
    return s;
  }
  if (table_grid != query_grid) {
    // 旧表不能跨网格生效；不得为匹配而平移 K。
    s.reason = "grid_mismatch";
    return s;
  }
  for (std::size_t i = 0; i < count_; ++i) {
    const Entry &e = entries_[i];
    const bool in_range =
        e.open_ended() ? target_tick >= e.first_target_tick
                       : (target_tick >= e.first_target_tick &&
                          target_tick <= e.last_target_tick);
    if (in_range) {
      s.valid = true;
      s.generation = e.generation;
      return s;
    }
  }
  // 表外不回退到最近一段
  s.reason = "target_outside_registered_plan";
  return s;
}

Digest Registry::content_digest(const Content &content) {
  Sha256 s;
  for (double v : content) append_be_double(s, v);
  return s.finish();
}

Digest Registry::table_digest() const {
  // 按 generation 升序：8 字节 BE generation || 32 字节 raw content digest
  // 先把 generation 排序，避免登记顺序影响摘要
  std::array<std::size_t, kMaxEntries> order{};
  for (std::size_t i = 0; i < count_; ++i) order[i] = i;
  for (std::size_t i = 1; i < count_; ++i)
    for (std::size_t j = i; j > 0 && entries_[order[j - 1]].generation >
                                        entries_[order[j]].generation;
         --j) {
      std::size_t t = order[j]; order[j] = order[j - 1]; order[j - 1] = t;
    }

  Sha256 s;
  for (std::size_t k = 0; k < count_; ++k) {
    const Entry &e = entries_[order[k]];
    append_be64(s, e.generation);
    const Digest d = content_digest(e.content);
    unsigned char raw[32];
    for (int i = 0; i < 32; ++i) {
      auto hex = [](char c) -> unsigned char {
        return c <= '9' ? static_cast<unsigned char>(c - '0')
                        : static_cast<unsigned char>(c - 'a' + 10);
      };
      raw[i] = static_cast<unsigned char>((hex(d[2 * i]) << 4) | hex(d[2 * i + 1]));
    }
    s.update(raw, 32);
  }
  return s.finish();
}

bool Registry::ranges_overlap(std::uint64_t a_first, std::uint64_t a_last,
                              std::uint64_t b_first, std::uint64_t b_last) const {
  // 0 表示开放式（到无穷）
  const bool a_open = (a_last == 0), b_open = (b_last == 0);
  if (!a_open && a_last < b_first) return false;
  if (!b_open && b_last < a_first) return false;
  return true;
}

void Registry::sorted_indices(std::size_t *order) const {
  for (std::size_t i = 0; i < count_; ++i) order[i] = i;
  for (std::size_t i = 1; i < count_; ++i)
    for (std::size_t j = i; j > 0 && entries_[order[j - 1]].generation >
                                        entries_[order[j]].generation;
         --j) {
      std::size_t t = order[j]; order[j] = order[j - 1]; order[j - 1] = t;
    }
}

Registry Registry::snapshot() const {
  // E06：深拷贝，事务持有自己的副本；冻结状态一并复制。
  Registry out;
  out.count_ = count_;
  out.frozen_ = frozen_;
  out.m0_content_ = m0_content_;
  for (std::size_t i = 0; i < count_; ++i) out.entries_[i] = entries_[i];
  return out;
}

bool Registry::structurally_valid() const {
  std::array<std::size_t, kMaxEntries> order{};
  sorted_indices(order.data());
  for (std::size_t i = 0; i < count_; ++i) {
    const Entry &a = entries_[order[i]];
    if (a.generation == 0) return false;
    if (!all_finite(a.content)) return false;
    for (std::size_t j = i + 1; j < count_; ++j) {
      const Entry &b = entries_[order[j]];
      if (a.generation == b.generation) return false;
      if (ranges_overlap(a.first_target_tick, a.last_target_tick,
                         b.first_target_tick, b.last_target_tick)) return false;
    }
  }
  return true;
}

std::string Registry::plan_canonical_json(const Grid &grid) const {
  // 132 的规范编码：字段顺序固定，无空白，无浮点。
  std::array<std::size_t, kMaxEntries> order{};
  sorted_indices(order.data());
  std::string out;
  auto num = [&](std::uint64_t v) { out += std::to_string(v); };
  out += "{\"grid\":{\"schedule_generation\":";
  num(grid.schedule_generation);
  out += ",\"clock_epoch\":";
  num(grid.clock_epoch);
  out += ",\"tick_period_ns\":";
  num(static_cast<std::uint64_t>(grid.tick_period_ns));
  out += ",\"deadline_ns\":";
  num(static_cast<std::uint64_t>(grid.deadline_ns));
  out += "},\"plan\":[";
  for (std::size_t k = 0; k < count_; ++k) {
    const Entry &e = entries_[order[k]];
    if (k) out += ',';
    out += "{\"generation\":";
    num(e.generation);
    out += ",\"first_target_tick\":";
    num(e.first_target_tick);
    out += ",\"last_target_tick\":";
    num(e.last_target_tick);
    out += '}';
  }
  out += "]}";
  return out;
}

Digest Registry::runtime_plan_digest_json_v1(const Grid &grid) const {
  // R01：这是**本头字段集**的 canonical JSON，不是 132 的编码。
  const std::string json = plan_canonical_json(grid);
  Sha256 s;
  s.update(reinterpret_cast<const unsigned char *>(json.data()), json.size());
  return s.finish();
}

Digest Registry::plan_fingerprint_be64_v1(const Grid &grid) const {
  // 计划身份必须覆盖 K 区间与 grid；与内容摘要分开。
  // 只改 K、内容不变时，本摘要必须变，table_digest 必须不变。
  std::array<std::size_t, kMaxEntries> order{};
  for (std::size_t i = 0; i < count_; ++i) order[i] = i;
  for (std::size_t i = 1; i < count_; ++i)
    for (std::size_t j = i; j > 0 && entries_[order[j - 1]].generation >
                                        entries_[order[j]].generation;
         --j) {
      std::size_t t = order[j]; order[j] = order[j - 1]; order[j - 1] = t;
    }

  Sha256 s;
  append_be64(s, grid.schedule_generation);
  append_be64(s, grid.clock_epoch);
  append_be64(s, static_cast<std::uint64_t>(grid.tick_period_ns));
  append_be64(s, static_cast<std::uint64_t>(grid.deadline_ns));
  for (std::size_t k = 0; k < count_; ++k) {
    const Entry &e = entries_[order[k]];
    append_be64(s, e.generation);
    append_be64(s, e.first_target_tick);
    append_be64(s, e.last_target_tick);  // 0 表示开放式
  }
  return s.finish();
}

// ---- 固定表内容（第131批 D02） ----------------------------------------
// 布局：19 hydro + 6 Q + 2 R + 2 Rd + 1 Qf_scale（与 p_global_pack.hpp 一致）
Content m0_content() {
  Content c{};
  const double hydro[19] = {
      14.2,      // mass
      2.13,      // Iz
      0.12,      // xg
      0.25,      // d_thruster
      -2.0,      // Xu_dot
      -8.0,      // Yv_dot
      -0.1817725,// Yr_dot
      -0.1817725,// Nv_dot
      -3.41,     // Nr_dot
      -2.272063, // Xu
      -2.629019, // Yv
      0.0,       // Yr
      0.0,       // Nv
      -3.105,    // Nr
      -11.571784,// Xuu
      -0.05,     // Yvv
      0.0,       // Yrr
      0.0,       // Nvv
      -0.71,     // Nrr
  };
  for (int i = 0; i < 19; ++i) c[i] = hydro[i];
  const double q[6] = {20.0, 20.0, 50.0, 8.0, 1.0, 8.0};
  for (int i = 0; i < 6; ++i) c[19 + i] = q[i];
  c[25] = 0.05; c[26] = 0.05;   // R
  c[27] = 0.2;  c[28] = 0.2;    // Rd
  c[29] = 8.0;                  // Qf_scale
  return c;
}

Content derive_m1_content(const Content &m0_base) {
  // M1 相对 M0 只改 mass=15.0、Xu=-2.4、Nr=-4.4
  Content c = m0_base;
  c[0] = 15.0;    // mass
  c[9] = -2.4;    // Xu
  c[13] = -4.4;   // Nr
  return c;
}

Content m1_content() {
  return derive_m1_content(m0_content());
}

Registry registry_from_m0(const Content &m0_base) {
  Registry r;
  r.m0_content_ = m0_base;
  // g1 -> M0 : target 1..5
  if (!r.register_generation(1, m0_base, 1, 5)) return Registry{};
  // g2 -> M1 : target 6..11
  if (!r.register_generation(2, derive_m1_content(m0_base), 6, 11)) return Registry{};
  // g3 -> M0 : target 12..（开放式）。内容与 g1 相同，但 generation 不同，
  // 因此保持**不同**的激活身份。
  if (!r.register_generation(3, m0_base, 12, 0)) return Registry{};
  r.freeze();
  return r;
}

Registry default_registry() {
  auto r = registry_from_m0(m0_content());
  // Legacy callers freeze the default table when they take their own snapshot.
  r.frozen_ = false;
  return r;
}

// ---- R01：132 语义 -> 运行结构的受检转换 -----------------------------
Digest Registry::content_digest_of_label(const std::string &label, bool *known) {
  if (known) *known = true;
  if (label == "M0") return content_digest(m0_content());
  if (label == "M1") return content_digest(m1_content());
  if (known) *known = false;
  return Digest{};
}

bool Registry::registered_content_digest_of_label(const std::string &label, Digest *out) const {
  if (label == "M0") {
    *out = content_digest(m0_content_);
  } else if (label == "M1") {
    *out = content_digest(derive_m1_content(m0_content_));
  } else {
    return false;
  }
  return true;
}

Registry::ConversionResult Registry::verify_plan_132_conversion(
    const Plan132Semantic &plan, const Grid &grid,
    const char *expected_contract_schema) const {
  ConversionResult r;
  const auto fail = [&](const char *why) { r.reason = why; return r; };

  if (plan.row_count == 0) return fail("empty_plan");
  if (plan.row_count > kMaxEntries) return fail("plan_too_large");
  if (plan.row_count != count_) return fail("plan_runtime_population_mismatch");
  if (plan.switch_count > kMaxEntries || plan.switch_count != plan.row_count - 1)
    return fail("switch_tick_count_mismatch");

  // grid 五个字段逐项一致
  if (plan.contract_schema.empty()) return fail("missing_contract_schema");
  // schema 必须精确等于冻结的合同身份（默认 v3）。只查非空会放行 v2。
  if (!expected_contract_schema || std::string(expected_contract_schema) != kFrozenContractSchema ||
      plan.contract_schema != kFrozenContractSchema)
    return fail("contract_schema_mismatch");
  if (plan.tick_period_ns != grid.tick_period_ns) return fail("grid_tick_period_mismatch");
  if (plan.deadline_ns != grid.deadline_ns) return fail("grid_deadline_mismatch");
  if (plan.schedule_generation_at_table_start != grid.schedule_generation)
    return fail("grid_schedule_generation_mismatch");
  if (plan.clock_epoch_at_table_start != grid.clock_epoch)
    return fail("grid_clock_epoch_mismatch");

  // 逐代：标签 -> 实际内容摘要 -> 区间
  for (std::size_t i = 0; i < plan.row_count; ++i) {
    const Plan132Row &row = plan.rows[i];
    if (row.generation == 0) return fail("zero_generation");
    if (i > 0 && row.generation <= plan.rows[i - 1].generation)
      return fail("generation_not_strictly_increasing");
    if (row.first_target_tick == 0) return fail("zero_first_target_tick");
    if (row.last_target_tick < -1) return fail("invalid_open_ended_encoding");
    if (row.last_target_tick >= 0 &&
        static_cast<std::uint64_t>(row.last_target_tick) < row.first_target_tick)
      return fail("invalid_target_interval");
    const Entry *e = find(row.generation);
    if (!e) return fail("generation_not_in_runtime_table");

    // content 标签必须映射到该代的实际内容
    Digest label_digest;
    if (!registered_content_digest_of_label(row.content_label, &label_digest))
      return fail("unknown_content_label");
    if (content_digest(e->content) != label_digest) return fail("content_label_digest_mismatch");

    // 区间
    if (e->first_target_tick != row.first_target_tick)
      return fail("first_target_tick_mismatch");
    // 132 的 null(-1) 必须对应运行表的 open_ended(0)，且只在转换层映射
    if (row.last_target_tick < 0) {
      if (!e->open_ended()) return fail("open_ended_mismatch");
    } else {
      if (e->open_ended() || e->last_target_tick !=
          static_cast<std::uint64_t>(row.last_target_tick))
        return fail("last_target_tick_mismatch");
    }

    // 与相邻行必须连续且不重叠
    if (i + 1 < plan.row_count) {
      if (row.last_target_tick < 0) return fail("open_ended_before_last_row");
      if (plan.rows[i + 1].first_target_tick !=
          static_cast<std::uint64_t>(row.last_target_tick) + 1)
        return fail("segments_not_contiguous");
      // 该边界必须出现在 switch_ticks 里
      if (plan.switch_ticks[i] != plan.rows[i + 1].first_target_tick)
        return fail("switch_tick_not_at_boundary");
    }
  }

  // Reconstruct the actual 132 field set, not the smaller runtime encoding.
  // Values reaching here are restricted to the two frozen labels and schema,
  // so no untrusted string can alter the canonical JSON syntax.
  std::string canonical = "{\"activation_plan\":[";
  for (std::size_t i = 0; i < plan.row_count; ++i) {
    const auto &row = plan.rows[i];
    if (i) canonical += ',';
    canonical += "{\"content\":\"" + row.content_label +
                 "\",\"first_target_tick\":" + std::to_string(row.first_target_tick) +
                 ",\"generation\":" + std::to_string(row.generation) +
                 ",\"last_target_tick\":";
    canonical += row.last_target_tick == -1 ? "null" : std::to_string(row.last_target_tick);
    canonical += '}';
  }
  canonical += "],\"grid\":{\"clock_epoch_at_table_start\":" +
               std::to_string(plan.clock_epoch_at_table_start) +
               ",\"contract_schema\":\"" + plan.contract_schema +
               "\",\"deadline_ns\":" + std::to_string(plan.deadline_ns) +
               ",\"schedule_generation_at_table_start\":" +
               std::to_string(plan.schedule_generation_at_table_start) +
               ",\"tick_period_ns\":" + std::to_string(plan.tick_period_ns) +
               "},\"switch_ticks\":[";
  for (std::size_t i = 0; i < plan.switch_count; ++i) {
    if (i) canonical += ',';
    canonical += std::to_string(plan.switch_ticks[i]);
  }
  canonical += "]}";
  Sha256 digest;
  digest.update(reinterpret_cast<const unsigned char *>(canonical.data()), canonical.size());
  r.canonical_preimage = std::move(canonical);
  r.semantic_sha256 = digest.finish();
  if (r.semantic_sha256 != kFrozen132SemanticSha256)
    return fail("frozen_132_semantic_digest_mismatch");

  r.ok = true;
  return r;
}

Registry::ConversionResult Registry::verify_plan_132_json(
    const std::string &preimage, const Grid &grid) const {
  ConversionResult invalid;
  auto fail = [&](const char *reason) { invalid.reason = reason; return invalid; };
  using Json = nlohmann::json;
  try {
    const auto j = Json::parse(preimage);
    const auto exact = [](const Json &object, std::initializer_list<const char *> keys) {
      if (!object.is_object() || object.size() != keys.size()) return false;
      for (const char *key : keys) if (!object.contains(key)) return false;
      return true;
    };
    if (!exact(j,{"activation_plan","grid","switch_ticks"}))
      return fail("plan_json_root_population");
    const auto &g=j.at("grid");
    if (!exact(g,{"clock_epoch_at_table_start","contract_schema","deadline_ns",
                  "schedule_generation_at_table_start","tick_period_ns"}))
      return fail("plan_json_grid_population");
    const auto &rows=j.at("activation_plan");const auto &switches=j.at("switch_ticks");
    if (!rows.is_array() || !switches.is_array() || rows.size()>kMaxEntries ||
        switches.size()>kMaxEntries) return fail("plan_json_array_population");
    Plan132Semantic plan{};plan.row_count=rows.size();plan.switch_count=switches.size();
    if (!g.at("contract_schema").is_string() ||
        !g.at("clock_epoch_at_table_start").is_number_unsigned() ||
        !g.at("schedule_generation_at_table_start").is_number_unsigned() ||
        !g.at("tick_period_ns").is_number_integer() ||
        !g.at("deadline_ns").is_number_integer()) return fail("plan_json_grid_types");
    plan.contract_schema=g.at("contract_schema").get<std::string>();
    plan.clock_epoch_at_table_start=g.at("clock_epoch_at_table_start").get<std::uint64_t>();
    plan.schedule_generation_at_table_start=g.at("schedule_generation_at_table_start").get<std::uint64_t>();
    plan.tick_period_ns=g.at("tick_period_ns").get<std::int64_t>();
    plan.deadline_ns=g.at("deadline_ns").get<std::int64_t>();
    for(std::size_t i=0;i<rows.size();++i) {
      const auto &row=rows.at(i);
      if(!exact(row,{"content","first_target_tick","generation","last_target_tick"}))
        return fail("plan_json_row_population");
      if(!row.at("content").is_string() || !row.at("first_target_tick").is_number_unsigned() ||
         !row.at("generation").is_number_unsigned() ||
         !(row.at("last_target_tick").is_null() || row.at("last_target_tick").is_number_unsigned()))
        return fail("plan_json_row_types");
      auto &dst=plan.rows[i];dst.content_label=row.at("content").get<std::string>();
      dst.first_target_tick=row.at("first_target_tick").get<std::uint64_t>();
      dst.generation=row.at("generation").get<std::uint64_t>();
      if(row.at("last_target_tick").is_null()) dst.last_target_tick=-1;
      else {
        const auto value=row.at("last_target_tick").get<std::uint64_t>();
        if(value>static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max()))
          return fail("plan_json_last_tick_overflow");
        dst.last_target_tick=static_cast<std::int64_t>(value);
      }
    }
    for(std::size_t i=0;i<switches.size();++i) {
      if(!switches.at(i).is_number_unsigned())return fail("plan_json_switch_type");
      plan.switch_ticks[i]=switches.at(i).get<std::uint64_t>();
    }
    auto result=verify_plan_132_conversion(plan,grid);
    if(result.ok && result.canonical_preimage!=preimage) return fail("plan_json_noncanonical_preimage");
    return result;
  } catch (const Json::exception &) { return fail("plan_json_invalid"); }
}

}  // namespace model_reference
