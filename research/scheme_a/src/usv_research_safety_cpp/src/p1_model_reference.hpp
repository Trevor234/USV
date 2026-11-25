// SPDX-License-Identifier: MIT
//
// model_reference_binding_v1.hpp — 有限模型表、内容/计划身份与目标模型解析。
//
// 来源：方案A 第131批 D02（模型表与激活计划）、第132批 A01（参考布局）、
//       A05（计划身份）、第133批 I00 的 T01/T04。
//
// 本头**故意不 include** 任何 130 角色头（p1_admission.hpp / raw_backend_v1.hpp）、
// Eigen、nlohmann/json、acados 或 ROS。理由：I01 的验收是"真实 C++ 函数、无 SDK"；
// 若它 include 130 头，会把"Admission 强制字节复用"这条约束拉进编译面。
// 调用方负责把自己的五轴版本映射到本头的 Axis 结构。
//
// 关键约束（不得改）：
//   * 模型表在启动前固定、有界；一代一内容，注册后不可改写。
//   * 解析器只返回"模型选择"，**不返回整个版本** —— 返回整个 Axes 会把
//     task/config/schedule/epoch 静默改回表初值。
//   * 默认关闭：`Options::model_switch_enabled` 的默认值是 false。
//     离线组件通过构造 Options 显式开启；**不得**改全局常量、**不得**新增 ROS 参数。
//   * 内容摘要与计划摘要分开：内容摘要只绑 generation + 30 维内容；
//     计划摘要另绑 K 区间与 grid。
//
#pragma once

#include <array>
#include <cstdint>
#include <cstddef>
#include <string>

namespace model_reference {

// ---- 30 维内容布局（与 p_global_pack.hpp 逐位一致） ---------------------
// 19 hydro + 6 Q + 2 R + 2 Rd + 1 Qf_scale
inline constexpr std::size_t kContentSize = 30;
using Content = std::array<double, kContentSize>;
Content m0_content();

// ---- 五轴版本 ----------------------------------------------------------
// 与 p1::Version 的字段顺序和含义相同，但本头自带一份，避免 include 130 头。
struct Axes {
  std::uint64_t task = 0;
  std::uint64_t model = 1;
  std::uint64_t config = 1;
  std::uint64_t schedule = 1;
  std::uint64_t epoch = 0;

  bool operator==(const Axes &o) const {
    return task == o.task && model == o.model && config == o.config &&
           schedule == o.schedule && epoch == o.epoch;
  }
  bool operator!=(const Axes &o) const { return !(*this == o); }
};

// ---- 网格身份 ----------------------------------------------------------
// 裸 tick 数字不构成身份：同一 tick 号可能属于另一个网格。
struct Grid {
  std::uint64_t schedule_generation = 1;
  std::uint64_t clock_epoch = 0;
  std::int64_t tick_period_ns = 200000000;
  std::int64_t deadline_ns = 150000000;

  bool operator==(const Grid &o) const {
    return schedule_generation == o.schedule_generation &&
           clock_epoch == o.clock_epoch &&
           tick_period_ns == o.tick_period_ns &&
           deadline_ns == o.deadline_ns;
  }
  bool operator!=(const Grid &o) const { return !(*this == o); }
};

// ---- 登记表 ------------------------------------------------------------
struct Entry {
  std::uint64_t generation = 0;   // 0 表示未登记
  Content content{};
  std::uint64_t first_target_tick = 0;
  std::uint64_t last_target_tick = 0;  // 0 表示"到无穷"
  bool open_ended() const { return last_target_tick == 0; }
};

// 表摘要与计划摘要的十六进制字符串
using Digest = std::string;

// ---- 解析结果 ----------------------------------------------------------
// **只返回模型选择**，不返回整个 Axes。
struct Selection {
  bool valid = false;
  std::uint64_t generation = 0;
  std::string reason;

  explicit operator bool() const { return valid; }
};

// ---- 选项（默认关闭） --------------------------------------------------
struct Options {
  // 默认关闭：普通角色不设置它，就得不到模型切换能力。
  // 离线组件通过构造显式开启，共用同一份真实函数。
  bool model_switch_enabled = false;
};

// ---- 有限表 ------------------------------------------------------------
class Registry {
 public:
  static constexpr std::size_t kMaxEntries = 8;

  Registry() = default;

  // 注册一代。规则：
  //   * **frozen 之后一律拒绝**（E06：这是执行约束，不是一个返回 false 的声明）；
  //   * generation 不得为 0；
  //   * 内容必须 30 维且全 finite；
  //   * 同一 generation 只登记一次；内容不同则拒绝（一代一内容，不可改写）；
  //   * 内容完全相同时重复登记是幂等的（合法等价表示）；
  //   * **区间不得重叠**（E06：重叠会让 resolve 有歧义）；
  //   * 表满（>= kMaxEntries）拒绝。
  bool register_generation(std::uint64_t generation, const Content &content,
                           std::uint64_t first_target_tick,
                           std::uint64_t last_target_tick);

  // ---- E06：真实冻结 ---------------------------------------------------
  // 与 `mutable_after_startup()`（一个 constexpr 声明）不同，这是**实例状态**：
  // freeze() 之后任何 register_generation 都返回 false。
  void freeze() { frozen_ = true; }
  bool frozen() const { return frozen_; }

  // 深拷贝快照：事务持有自己的不可变副本，而不是 const&。
  Registry snapshot() const;
  bool structurally_valid() const;   // 无重叠、区间有序、generation 唯一

  // 只读注册状态：返回是否已登记该 generation，不暴露可写内容。
  bool is_registered(std::uint64_t generation) const;
  std::size_t size() const { return count_; }
  const Entry *find(std::uint64_t generation) const;

  // 目标模型解析：只返回模型选择。
  //   * 未登记 / 零代 -> 拒绝；
  //   * 目标 tick 不在任何区间 -> 拒绝（**不得**回退到最近一段，**不得**平移 K）；
  //   * grid 不匹配 -> 拒绝（旧表不能跨网格生效）；
  //   * target_tick == 0 -> 拒绝，理由为 "no_job_at_target_zero"。
  //     这是**计划**层面的拒绝，不是启动错误：首个模型来自构造初始化，
  //     Job 计划从 target 1 起。调用方不得把它当成致命错误。
  Selection resolve(const Grid &table_grid, const Grid &query_grid,
                    std::uint64_t target_tick, const Options &opts) const;

  // 内容摘要：SHA-256 over 30 个 big-endian binary64（与 p_global_pack 顺序一致）。
  static Digest content_digest(const Content &content);

  // 表摘要：按 generation 升序，每代 8 字节 BE generation || 32 字节 raw content digest。
  Digest table_digest() const;

  // ---- 计划身份：四个不同的身份，四个不同的名字（R01） ----------------
  //
  // 134 的注释曾声称 `plan_digest` 就是"132 的规范 JSON 编码"。那是**错的**：
  // 132 的 preimage 含 content 标签、contract_schema、switch_ticks，开放上界是
  // null；本头的字段集更小、开放上界是 0。两者是不同的 schema，不是空白差异。
  //
  // 四类身份实测值（同一计划）：
  //   plan_file_sha256            7a5a4289…   132 文件字节
  //   plan_semantic_132_sha256    63a1696d…   132 preimage 的语义编码
  //   runtime_plan_digest_json_v1 01374714…   本头字段集的 canonical JSON
  //   plan_fingerprint_be64_v1    cd366a68…   本头字段集的 BE64
  //
  // 前三者的关系由 verify_plan_132_conversion() 受检建立；**不得**断言后两者
  // 与第二者相等，也不得靠重命名宣布认证完成。

  // 本头字段集的 canonical JSON 摘要（**不是** 132 的编码）。
  Digest runtime_plan_digest_json_v1(const Grid &grid) const;

  // 本头字段集的 BE64 二进制指纹。
  Digest plan_fingerprint_be64_v1(const Grid &grid) const;

  // 本头字段集的规范 JSON 文本（不含空白差异）。
  std::string plan_canonical_json(const Grid &grid) const;

  // ---- R01：132 语义计划 -> 运行结构的受检转换 ------------------------
  // 输入是 132 preimage 的**语义**（content 标签、null 开放上界、switch_ticks），
  // 输出是本头的字段集。转换逐项检查；任何不一致返回空 reason 之外的具体原因。
  struct Plan132Row {
    std::string content_label;         // "M0" / "M1"
    std::uint64_t generation = 0;
    std::uint64_t first_target_tick = 0;
    std::int64_t last_target_tick = -1;  // -1 = null (open ended)
  };
  struct Plan132Semantic {
    Plan132Row rows[Registry::kMaxEntries]{};
    std::size_t row_count = 0;
    std::uint64_t switch_ticks[Registry::kMaxEntries]{};
    std::size_t switch_count = 0;
    std::string contract_schema;
    std::int64_t tick_period_ns = 0;
    std::int64_t deadline_ns = 0;
    std::uint64_t schedule_generation_at_table_start = 0;
    std::uint64_t clock_epoch_at_table_start = 0;
  };
  struct ConversionResult {
    bool ok = false;
    std::string reason;
    std::string canonical_preimage;
    Digest semantic_sha256;
  };

  // 用运行表与 grid 校验一份 132 语义计划：
  //   * 每个 content 标签必须映射到该 generation 的实际 content_digest；
  //   * switch_ticks 必须等于相邻区间的边界（last+1）；
  //   * grid 五个字段逐项一致；
  //   * 132 的 null 上界必须对应本头的 open_ended()；
  //   * 区间必须连续、不重叠、generation 唯一。
  // 132 preimage 里的 contract_schema 是**冻结身份**。运行表本身不携带它，
  // 所以必须显式给出期望值；默认值固定为 v3，改动它就是一次合同修订。
  static constexpr const char *kFrozenContractSchema = "p1-execution-contract-v3";
  static constexpr const char *kFrozen132SemanticSha256 =
      "63a1696dd7f597670642b67ea4f143910af5111effddb3ce923e56a5dd9e52f9";

  ConversionResult verify_plan_132_conversion(
      const Plan132Semantic &plan, const Grid &grid,
      const char *expected_contract_schema = kFrozenContractSchema) const;
  // Parse the frozen preimage itself, including exact field populations; a
  // default-initialized semantic field must not stand in for a missing key.
  ConversionResult verify_plan_132_json(const std::string &preimage, const Grid &grid) const;

  // 供测试直接取某个 content 标签的期望摘要（M0/M1），用于标签绑定断言。
  static Digest content_digest_of_label(const std::string &label, bool *known = nullptr);
  bool registered_content_digest_of_label(const std::string &label, Digest *out) const;

  // 保留原名，但**不再是唯一保障**：真正的约束是 frozen()。
  // 测试必须断言 freeze() 后的拒绝，而不是断言这个常量。
  static constexpr bool mutable_after_startup() { return false; }

 private:
  friend Registry registry_from_m0(const Content &m0_base);
  friend Registry default_registry();
  bool content_equal(const Content &a, const Content &b) const;
  static bool all_finite(const Content &c);
  bool ranges_overlap(std::uint64_t a_first, std::uint64_t a_last,
                      std::uint64_t b_first, std::uint64_t b_last) const;
  void sorted_indices(std::size_t *order) const;

  Entry entries_[kMaxEntries]{};
  Content m0_content_ = m0_content();
  std::size_t count_ = 0;
  bool frozen_ = false;          // E06：实例级冻结状态
};

// ---- 默认构造的登记表（与第131批 D02 的固定表一致） -------------------
// g1 -> M0 (target 1..5), g2 -> M1 (target 6..11), g3 -> M0 (target 12..)
// 内容相同的 g1 与 g3 保持**不同**的激活身份。
Content derive_m1_content(const Content &m0_base);
Content m1_content();
Registry registry_from_m0(const Content &m0_base);
Registry default_registry();

}  // namespace model_reference
