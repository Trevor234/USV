// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT
//
// p1_clock_diagnostics.hpp —— 时钟断档诊断的**纯观测**仪表（无 ROS、无 DDS）。
//
// 目的：把"发布侧实际时刻"和"接收侧实际入口时刻"分别落在同一个
// CLOCK_MONOTONIC 时基上，使 450 ms 这类**映射时间**差不再被当成墙钟停顿。
//
// 三条硬约束：
//   1. 空路径 = 完全禁用：不分配缓冲、不额外读时钟、不创建文件。
//   2. 热路径只写 POD 与计数：不分配、不加新锁、不做 JSON、不做文件 I/O。
//   3. 缓冲**饱和即停**：满后只增 dropped，绝不循环覆盖旧记录，也绝不改
//      任何控制状态。
//
// 因此这里既不用 Regulator 的 Sink（会构造 JSON 且溢出影响控制），也不用
// plant 的 event()（同步写盘 + flush）。
#pragma once

#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <memory>
#include <string>
#include <vector>

#include <fcntl.h>
#include <time.h>
#include <unistd.h>

#include <nlohmann/json.hpp>

namespace p1_clock_diag
{

/// 全部诊断行共用 CLOCK_MONOTONIC；at_ns 是**调用现场**采样值。
inline std::int64_t monotonic_ns() noexcept
{
  timespec t{};
  clock_gettime(CLOCK_MONOTONIC, &t);
  return std::int64_t(t.tv_sec) * 1000000000LL + std::int64_t(t.tv_nsec);
}

enum StreamId : std::uint8_t
{
  kPlantExecutor = 0,
  kRegulatorCallbacks = 1,
  kRegulatorTick = 2,
};

inline const char * stream_name(std::uint8_t id) noexcept
{
  switch (id) {
    case kPlantExecutor: return "plant_executor";
    case kRegulatorCallbacks: return "regulator_callbacks";
    case kRegulatorTick: return "regulator_tick";
    default: return "unknown";
  }
}

enum EventId : std::uint16_t
{
  kPumpBegin = 1,
  kPumpLocked,
  kPumpEnd,
  kStepBegin,
  kStepEnd,
  kReceiveBegin,
  kReceiveLocked,
  kReceiveEnd,
  kClockPublishBegin,
  kClockPublishEnd,
  kPublishBegin,
  kPublishEnd,
  kSourceIoBegin,
  kSourceIOLocked,
  kSourceIoEnd,
  kClockResync,
  kClockCallbackBegin,
  kClockCallbackLocked,
  kClockCallbackEnd,
  kTickBegin,
  kTickLocked,
  kTickEnd,
  kReceiptCallbackBegin,
  kReceiptCallbackLocked,
  kReceiptCallbackEnd,
  kHoldCloseCallbackBegin,
  kHoldCloseCallbackLocked,
  kHoldCloseCallbackEnd,
  kCallbackBegin,
  kCallbackEnd,
  kPause,
  kResume,
  kClockEpochChange,
  kScheduleReset,
};

inline const char * event_name(std::uint16_t id) noexcept
{
  switch (id) {
    case kPumpBegin: return "pump_begin";
    case kPumpLocked: return "pump_locked";
    case kPumpEnd: return "pump_end";
    case kStepBegin: return "step_begin";
    case kStepEnd: return "step_end";
    case kReceiveBegin: return "receive_begin";
    case kReceiveLocked: return "receive_locked";
    case kReceiveEnd: return "receive_end";
    case kClockPublishBegin: return "clock_publish_begin";
    case kClockPublishEnd: return "clock_publish_end";
    case kPublishBegin: return "publish_begin";
    case kPublishEnd: return "publish_end";
    case kSourceIoBegin: return "source_io_begin";
    case kSourceIOLocked: return "source_io_locked";
    case kSourceIoEnd: return "source_io_end";
    case kClockResync: return "clock_resync";
    case kClockCallbackBegin: return "clock_callback_begin";
    case kClockCallbackLocked: return "clock_callback_locked";
    case kClockCallbackEnd: return "clock_callback_end";
    case kTickBegin: return "tick_begin";
    case kTickLocked: return "tick_locked";
    case kTickEnd: return "tick_end";
    case kReceiptCallbackBegin: return "receipt_callback_begin";
    case kReceiptCallbackLocked: return "receipt_callback_locked";
    case kReceiptCallbackEnd: return "receipt_callback_end";
    case kHoldCloseCallbackBegin: return "hold_close_callback_begin";
    case kHoldCloseCallbackLocked: return "hold_close_callback_locked";
    case kHoldCloseCallbackEnd: return "hold_close_callback_end";
    case kCallbackBegin: return "callback_begin";
    case kCallbackEnd: return "callback_end";
    case kPause: return "pause";
    case kResume: return "resume";
    case kClockEpochChange: return "clock_epoch_change";
    case kScheduleReset: return "schedule_reset";
    default: return "unknown";
  }
}

enum KindId : std::uint16_t
{
  kNoKind = 0,
  kKindPump,
  kKindReceiveCatchup,
  kKindReceiveScheduled,
  kKindClock,
  kKindOdom,
  kKindImu,
  kKindPath,
  kKindProfile,
  kKindCandidate,
  kKindCapability,
  kKindStop,
  kKindOkReceipt,
  kKindRejectionReceipt,
  kKindHoldClose,
  kKindBootstrap,
  kKindPlantCommand,
  kKindDecision,
  kKindApplied,
};

inline const char * kind_name(std::uint16_t id) noexcept
{
  switch (id) {
    case kKindPump: return "pump";
    case kKindReceiveCatchup: return "receive_catchup";
    case kKindReceiveScheduled: return "receive_scheduled";
    case kKindClock: return "clock";
    case kKindOdom: return "odom";
    case kKindImu: return "imu";
    case kKindPath: return "path";
    case kKindProfile: return "profile";
    case kKindCandidate: return "candidate";
    case kKindCapability: return "capability";
    case kKindStop: return "stop";
    case kKindOkReceipt: return "ok_receipt";
    case kKindRejectionReceipt: return "rejection_receipt";
    case kKindHoldClose: return "hold_close";
    case kKindBootstrap: return "bootstrap_receipt";
    case kKindPlantCommand: return "plant_command";
    case kKindDecision: return "decision";
    case kKindApplied: return "applied";
    default: return "none";
  }
}

enum ExitId : std::uint16_t
{
  kExitNone = 0,
  kExitIdleNotDue,
  kExitStepped,
  kExitStopping,
  kExitStepFailed,
};

inline const char * exit_name(std::uint16_t id) noexcept
{
  switch (id) {
    case kExitIdleNotDue: return "idle_not_due";
    case kExitStepped: return "stepped";
    case kExitStopping: return "stopping";
    case kExitStepFailed: return "step_failed";
    default: return "none";
  }
}

enum DispositionId : std::uint16_t
{
  kDispNone = 0,
  kDispOk,
  kDispRejected,
  kDispLate,
  kDispDuplicate,
  kDispBootstrap,
  kDispForeign,
};

inline const char * disposition_name(std::uint16_t id) noexcept
{
  switch (id) {
    case kDispOk: return "ok";
    case kDispRejected: return "rejected";
    case kDispLate: return "late";
    case kDispDuplicate: return "duplicate";
    case kDispBootstrap: return "bootstrap";
    case kDispForeign: return "foreign";
    default: return "";
  }
}

/// 定长 payload：绝不保存悬空 std::string 指针。
constexpr std::size_t kTextBytes = 112;

struct TraceRecord
{
  std::uint16_t event = 0;
  std::uint16_t kind = 0;
  std::uint16_t exit = 0;
  std::uint16_t disposition = 0;
  std::uint8_t stream = 0;
  std::uint8_t flags = 0;
  std::uint16_t pad = 0;
  std::uint32_t seq = 0;
  std::uint32_t call_id = 0;
  std::uint32_t span_id = 0;
  std::uint32_t reserved = 0;
  std::int64_t at_ns = 0;
  std::int64_t sim_ns = 0;
  std::int64_t mapped_steady_ns = 0;
  std::int64_t origin_ns = 0;
  std::int64_t a = 0;
  std::int64_t b = 0;
  std::int64_t c = 0;
  std::int64_t d = 0;
  std::uint64_t identity_a = 0;
  std::uint64_t identity_b = 0;
  std::uint64_t schedule_runtime = 0;
  std::uint64_t schedule_grid = 0;
  std::uint64_t epoch = 0;
  char text[kTextBytes] = {0};
};

enum FlagBits : std::uint8_t
{
  kHasSim = 1U << 0,
  kHasMapped = 1U << 1,
  kTextTruncated = 1U << 2,
  kHasIdentity = 1U << 3,
  kHasSchedule = 1U << 4,
};

static_assert(sizeof(TraceRecord) <= 256, "trace record must stay inside the fixed budget");
static_assert(kTextBytes + 144 >= sizeof(TraceRecord), "unexpected record growth");

/// 链式构造只在采样现场拼一个 POD，不分配。
class Record
{
 public:
  Record(EventId event, std::uint8_t stream, std::int64_t at_ns) noexcept
  {
    r_.event = event;
    r_.stream = stream;
    r_.at_ns = at_ns;
  }

  Record & call(std::uint32_t id) noexcept { r_.call_id = id; return *this; }
  Record & span(std::uint32_t id) noexcept { r_.span_id = id; return *this; }
  Record & kind(KindId id) noexcept { r_.kind = id; return *this; }
  Record & exit(ExitId id) noexcept { r_.exit = id; return *this; }
  Record & disposition(DispositionId id) noexcept { r_.disposition = id; return *this; }
  Record & sim(std::int64_t value) noexcept { r_.sim_ns = value; r_.flags |= kHasSim; return *this; }

  /// 只有映射时刻必须与前缀 origin 同行出现，才能逐段校验 mapped=origin+sim。
  Record & mapped(std::int64_t value, std::int64_t origin) noexcept
  {
    r_.mapped_steady_ns = value;
    r_.origin_ns = origin;
    r_.flags |= kHasMapped;
    return *this;
  }

  Record & nums(std::int64_t a, std::int64_t b) noexcept
  {
    r_.a = a;
    r_.b = b;
    return *this;
  }

  Record & nums(std::int64_t a, std::int64_t b, std::int64_t c, std::int64_t d) noexcept
  {
    r_.a = a;
    r_.b = b;
    r_.c = c;
    r_.d = d;
    return *this;
  }

  Record & ident(std::uint64_t a, std::uint64_t b) noexcept
  {
    r_.identity_a = a;
    r_.identity_b = b;
    r_.flags |= kHasIdentity;
    return *this;
  }

  Record & schedule(std::uint64_t runtime, std::uint64_t grid, std::uint64_t epoch) noexcept
  {
    r_.schedule_runtime = runtime;
    r_.schedule_grid = grid;
    r_.epoch = epoch;
    r_.flags |= kHasSchedule;
    return *this;
  }

  /// 超长 reason 显式标记截断，使证据在分析侧被判为不完整，而不是被静默截短。
  Record & text(const char * value) noexcept
  {
    if (value == nullptr || *value == '\0') return *this;
    const std::size_t len = std::strlen(value);
    const std::size_t copy = len < kTextBytes - 1 ? len : kTextBytes - 1;
    std::memcpy(r_.text, value, copy);
    r_.text[copy] = '\0';
    if (copy != len) r_.flags |= kTextTruncated;
    return *this;
  }

  Record & text(const std::string & value) noexcept { return text(value.c_str()); }

  const TraceRecord & get() const noexcept { return r_; }

 private:
  TraceRecord r_{};
};

/// 计数与缓冲同行，flush 侧只读指针，不再维护第二份可能漂移的副本。
struct TraceCounters
{
  std::uint32_t stored = 0;
  std::uint32_t attempted = 0;
  std::uint32_t dropped = 0;
  std::uint32_t calls = 0;
};

/// 定长饱和缓冲：满后只增加 dropped，不覆盖、不放宽、不改控制状态。
template <std::size_t Capacity>
class BoundedTrace
{
 public:
  BoundedTrace() : data_(std::make_unique<TraceRecord[]>(Capacity)) { touch(); }

  BoundedTrace(const BoundedTrace &) = delete;
  BoundedTrace & operator=(const BoundedTrace &) = delete;

  /// 热路径：一次 POD 拷贝 + 三个计数，无分配、无锁、无 I/O。
  void append(const TraceRecord & record) noexcept
  {
    ++counters_.attempted;
    if (counters_.stored < Capacity) {
      TraceRecord & slot = data_[counters_.stored];
      slot = record;
      slot.seq = counters_.stored + 1;
      ++counters_.stored;
      return;
    }
    ++counters_.dropped;
  }

  std::uint32_t next_call() noexcept { return ++counters_.calls; }

  const TraceRecord * data() const noexcept { return data_.get(); }
  std::size_t capacity() const noexcept { return Capacity; }
  const TraceCounters & counters() const noexcept { return counters_; }
  std::uint32_t stored() const noexcept { return counters_.stored; }
  std::uint32_t attempted() const noexcept { return counters_.attempted; }
  std::uint32_t dropped() const noexcept { return counters_.dropped; }
  bool complete() const noexcept
  {
    return counters_.dropped == 0 && counters_.stored == counters_.attempted;
  }

 private:
  /// 启动时一次性触碰整块内存：此后热路径不会再触发缺页。
  void touch() noexcept
  {
    for (std::size_t i = 0; i < Capacity; ++i) data_[i] = TraceRecord{};
  }

  std::unique_ptr<TraceRecord[]> data_;
  TraceCounters counters_;
};

/// 一个已注册的流：只持有指针，flush 时在**没有 writer** 的调用点读取计数。
struct StreamView
{
  const char * name = nullptr;
  const TraceRecord * data = nullptr;
  std::size_t capacity = 0;
  const TraceCounters * counters = nullptr;
};

/// 文件句柄 + 头行 + 末行 summary。写出与析构兜底都 noexcept / 幂等。
class Diagnostics
{
 public:
  static constexpr const char * kSchema = "scheme-a-clock-diagnostics-v1";

  /// 排他创建：路径缺父目录、已有文件或不可写都必须**显式失败**，不静默禁用。
  static std::unique_ptr<Diagnostics> create(const std::string & path, const nlohmann::json & header)
  {
    const int fd = ::open(path.c_str(), O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0644);
    if (fd < 0) {
      throw std::runtime_error(
              std::string("clock diagnostics file must be new and writable: ") + path +
              ": " + std::strerror(errno));
    }
    std::FILE * file = ::fdopen(fd, "w");
    if (file == nullptr) {
      const int saved = errno;
      ::close(fd);
      throw std::runtime_error(
              std::string("clock diagnostics fdopen failed: ") + path + ": " + std::strerror(saved));
    }
    std::unique_ptr<Diagnostics> out(new Diagnostics(path, file));
    nlohmann::json line = header;
    line["type"] = "clock_diagnostics_header";
    line["schema"] = kSchema;
    line["clock"] = "CLOCK_MONOTONIC";
    if (!out->write_line(line)) {
      throw std::runtime_error("clock diagnostics header write failed: " + path);
    }
    return out;
  }

  Diagnostics(const Diagnostics &) = delete;
  Diagnostics & operator=(const Diagnostics &) = delete;

  ~Diagnostics() { flush(); }

  template <std::size_t Capacity>
  void add_stream(const char * name, const BoundedTrace<Capacity> & trace)
  {
    StreamView view;
    view.name = name;
    view.data = trace.data();
    view.capacity = trace.capacity();
    view.counters = &trace.counters();
    streams_.push_back(view);
  }

  /// 幂等：第二次调用直接返回首次结果，不重复写 summary。
  bool flush() noexcept
  {
    if (flushed_) return flush_ok_;
    flushed_ = true;
    flush_ok_ = false;
    if (file_ == nullptr) return false;
    bool ok = true;
    std::uint64_t attempted = 0, stored = 0, dropped = 0;
    for (const auto & view : streams_) {
      for (std::uint32_t i = 0; i < view.counters->stored; ++i) {
        if (!write_record(view, view.data[i])) ok = false;
      }
      attempted += view.counters->attempted;
      stored += view.counters->stored;
      dropped += view.counters->dropped;
    }
    nlohmann::json summary;
    summary["type"] = "clock_diagnostics_summary";
    summary["schema"] = kSchema;
    summary["attempted"] = attempted;
    summary["stored"] = stored;
    summary["dropped"] = dropped;
    summary["complete"] = ok && dropped == 0 && stored == attempted;
    summary["streams"] = nlohmann::json::array();
    for (const auto & view : streams_) {
      summary["streams"].push_back({{"stream", view.name},
                                    {"capacity", view.capacity},
                                    {"attempted", view.counters->attempted},
                                    {"stored", view.counters->stored},
                                    {"dropped", view.counters->dropped},
                                    {"complete", view.counters->dropped == 0 &&
                                                   view.counters->stored ==
                                                     view.counters->attempted}});
    }
    summary["finished_ns"] = monotonic_ns();
    if (!write_line(summary)) ok = false;
    if (std::fflush(file_) != 0) ok = false;
    if (std::fclose(file_) != 0) ok = false;
    file_ = nullptr;
    flush_ok_ = ok;
    return ok;
  }

  bool flushed() const noexcept { return flushed_; }
  bool flush_ok() const noexcept { return flush_ok_; }
  const std::string & path() const noexcept { return path_; }

  /// 仅供测试注入 I/O 失败：让"写失败绝不冒充成功"可被确定性验证。
  std::FILE * file_for_test() const noexcept { return file_; }

 private:
  Diagnostics(std::string path, std::FILE * file) : path_(std::move(path)), file_(file) {}

  bool write_line(const nlohmann::json & line) noexcept
  {
    if (file_ == nullptr) return false;
    const std::string text = line.dump();
    if (std::fwrite(text.data(), 1, text.size(), file_) != text.size()) return false;
    return std::fputc('\n', file_) != EOF;
  }

  bool write_record(const StreamView & view, const TraceRecord & record) noexcept
  {
    nlohmann::json line;
    line["type"] = "clock_diagnostics";
    line["event"] = event_name(record.event);
    line["stream"] = view.name;
    line["seq"] = record.seq;
    line["call_id"] = record.call_id;
    line["span_id"] = record.span_id;
    line["at_ns"] = record.at_ns;
    if (record.flags & kHasSim) line["sim_ns"] = record.sim_ns;
    if (record.flags & kHasMapped) {
      line["mapped_steady_ns"] = record.mapped_steady_ns;
      line["origin_ns"] = record.origin_ns;
    }
    if (record.kind != 0) line["kind"] = kind_name(record.kind);
    if (record.exit != 0) line["exit_reason"] = exit_name(record.exit);
    if (record.disposition != 0) line["disposition"] = disposition_name(record.disposition);
    record_fields(line, record);
    if (record.text[0] != '\0') line["reason"] = record.text;
    if (record.flags & kTextTruncated) line["reason_truncated"] = true;
    return write_line(line);
  }

  /// 每个事件的语义字段名固定在这里，分析脚本按名字读，不靠猜测位置。
  static void record_fields(nlohmann::json & line, const TraceRecord & record) noexcept
  {
    const auto ids = [&]() {
      line["identity_a"] = record.identity_a;
      line["identity_b"] = record.identity_b;
    };
    const auto nums = [&]() {
      line["a"] = record.a;
      line["b"] = record.b;
      line["c"] = record.c;
      line["d"] = record.d;
    };
    const auto sched = [&]() {
      line["schedule_runtime"] = record.schedule_runtime;
      line["schedule_grid"] = record.schedule_grid;
      line["epoch"] = record.epoch;
    };
    switch (record.event) {
      case kPumpBegin:
        break;
      case kPumpLocked:
        break;
      case kPumpEnd:
        break;
      case kStepBegin:
      case kStepEnd:
        line["sim_before_ns"] = record.a;
        line["substeps"] = record.b;
        break;
      case kReceiveBegin:
        line["command_sequence"] = record.identity_a;
        line["command_tick"] = record.identity_b;
        break;
      case kReceiveLocked:
        line["sim_before_ns"] = record.a;
        line["scheduled_sequence"] = record.b;
        line["advance_substeps"] = record.c;
        break;
      case kReceiveEnd:
        line["executes"] = record.a != 0;
        line["catch_up_substeps"] = record.c;
        line["scheduled_substeps"] = record.d;
        line["pending_sequence"] = record.identity_a;
        line["execution_index"] = record.identity_b;
        break;
      case kClockPublishBegin:
      case kClockPublishEnd:
        break;
      case kPublishBegin:
      case kPublishEnd:
        ids();
        break;
      case kSourceIoBegin:
      case kSourceIOLocked:
      case kSourceIoEnd:
        line["flush"] = record.a != 0;
        break;
      case kClockResync:
        line["old_origin_ns"] = record.a;
        line["new_origin_ns"] = record.b;
        break;
      case kClockCallbackBegin:
      case kClockCallbackLocked:
      case kClockCallbackEnd:
        line["previous_sim_ns"] = record.a;
        line["previous_receive_ns"] = record.b;
        line["last_advance_ns"] = record.identity_a;
        sched();
        break;
      case kTickBegin:
      case kTickLocked:
      case kTickEnd:
        line["tick"] = record.identity_a;
        line["decision_sequence"] = record.identity_b;
        line["planned_ns"] = record.a;
        line["start_ns"] = record.b;
        line["end_ns"] = record.c;
        sched();
        break;
      case kReceiptCallbackBegin:
      case kReceiptCallbackLocked:
      case kReceiptCallbackEnd:
        line["sequence"] = record.identity_a;
        line["execution_index"] = record.identity_b;
        line["accepted"] = record.a != 0;
        break;
      case kHoldCloseCallbackBegin:
      case kHoldCloseCallbackLocked:
      case kHoldCloseCallbackEnd:
        line["execution_index"] = record.identity_a;
        line["truncated"] = record.a != 0;
        break;
      case kCallbackBegin:
      case kCallbackEnd:
        break;
      case kPause:
      case kResume:
      case kClockEpochChange:
        line["previous_sim_ns"] = record.a;
        line["last_advance_ns"] = record.identity_a;
        line["threshold_ns"] = record.identity_b;
        sched();
        break;
      case kScheduleReset:
        line["last_schedule"] = record.identity_a;
        line["tick_before"] = record.a;
        line["tick_after"] = record.b;
        line["origin_before_ns"] = record.c;
        line["origin_after_ns"] = record.d;
        sched();
        break;
      default:
        nums();
        break;
    }
  }

  std::string path_;
  std::FILE * file_ = nullptr;
  std::vector<StreamView> streams_;
  bool flushed_ = false;
  bool flush_ok_ = false;
};

}  // namespace p1_clock_diag
