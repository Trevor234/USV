// Copyright 2026 USV Developer
//
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files (the "Software"), to deal
// in the Software without restriction, including without limitation the rights
// to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
// copies of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:
//
// The above copyright notice and this permission notice shall be included in
// all copies or substantial portions of the Software.
//
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
// IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
// THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
// OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
// THE SOFTWARE.

/**
 * @file benchmark_solver.cpp
 * @brief 动力学 NMPC (方案 B) 固定输入数值/耗时基线诊断程序。
 *
 * 仅用于同一冻结源码的 NoOpt 与 Release 两套构建离线对照, 不安装、不参与
 * 生产控制链路, 默认不构建 (需 -DUSV_BUILD_BASELINE_BENCHMARK=ON)。
 *
 * 参数一律从部署期 mpc_params_B.yaml / usv_params_B.yaml 读取 (与节点
 * init_mpc_solver_() 同一套字段映射, 含全部 19 个水动力字段), 不创建 ROS
 * 通信节点, 不使用结构体默认值替代冻结 YAML。
 *
 * 方案 B 只有 acados 后端 (本包未包含 CasADi 实现); --backend casadi 会
 * 明确失败, 不会把 acados 结果记成 casadi。
 *
 * 用法:
 *   benchmark_dynamic_solver --params <mpc_params_B.yaml>
 *     --vehicle <usv_params_B.yaml> --backend acados
 *     --phase numerical|timing --output <新的 JSON 路径>
 *
 *   # 逐拍重放旧 numerical.json 的 measured/reference/anchor (仅 numerical)
 *   benchmark_dynamic_solver ... --phase numerical \
 *     --replay-inputs <旧 numerical.json> --output <新的 JSON 路径>
 */

#include <Eigen/Dense>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <fstream>
#include <map>
#include <memory>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include <nlohmann/json.hpp>
#include <rclcpp/parameter_map.hpp>
#include <rclcpp/parameter.hpp>

#include "usv_nmpc/acados_backend.hpp"
#include "usv_nmpc/mpc_solver.hpp"

namespace
{

using json = nlohmann::json;

/// 场景数量: 直线 / 圆弧 / 跨 ±π 圆弧 / 直线+非零锚点。
constexpr int kScenarioCount = 4;
/// 计时阶段 (计划固定值, 不提供调参入口)。
constexpr int kTimingWarmup = 20;
constexpr int kTimingMeasured = 500;
/// 数值阶段每场景拍数 (含完整热启动链)。
constexpr int kNumericalSteps = 5;
/// 测量位置沿曲线法向的固定偏移 (m)。
constexpr double kMeasurementOffsetM = 0.2;
/// 计时阶段采样记录的输入拍号。
const std::vector<int> kSampledInputSteps = {0, 64, 128, 256, 384, 511};
/// 场景 1..3 的固定推力锚点; 场景 4 用非零偏置锚点。
constexpr double kAnchorNominalN = 5.0;
constexpr double kAnchorOffsetLeftN = 5.0;
constexpr double kAnchorOffsetRightN = -5.0;

[[noreturn]] void Fail(const std::string & message)
{
  throw std::runtime_error(message);
}

double WrapPi(double angle)
{
  double wrapped = std::fmod(angle + M_PI, 2.0 * M_PI);
  if (wrapped < 0.0) {
    wrapped += 2.0 * M_PI;
  }
  return wrapped - M_PI;
}

// ── 参数读取: 与 rclcpp 节点同样的 YAML 解析与字段映射 ──────────────
class ParamStore {
public:
  explicit ParamStore(const std::vector<std::string> & yaml_files)
  {
    for (const auto & file : yaml_files) {
      const auto map = rclcpp::parameter_map_from_yaml_file(file, kNodeName);
      for (const auto & param : rclcpp::parameters_from_map(map, kNodeName)) {
        // 与 launch 的参数列表语义一致: 后加载的文件覆盖先加载的同名值。
        values_[param.get_name()] = param;
      }
    }
    if (values_.empty()) {
      Fail("参数文件解析后为空: " + yaml_files.front());
    }
  }

  double AsDouble(const std::string & name) const
  {
    return Require(name).as_double();
  }

  int AsInt(const std::string & name) const
  {
    return static_cast<int>(Require(name).as_int());
  }

  std::vector<double> AsDoubleArray(const std::string & name) const
  {
    return Require(name).as_double_array();
  }

private:
  static constexpr const char * kNodeName = "/mpc_controller_node";

  const rclcpp::Parameter & Require(const std::string & name) const
  {
    const auto it = values_.find(name);
    if (it == values_.end()) {
      Fail("参数文件缺少字段: " + name);
    }
    return it->second;
  }

  std::map<std::string, rclcpp::Parameter> values_;
};

// ── 固定输入场景 ────────────────────────────────────────────────────
struct ScenarioSpec
{
  const char * name;
  bool arc;
  double rotation;
  bool custom_anchor;
};

struct CurvePoint
{
  double x = 0.0;
  double y = 0.0;
  double psi = 0.0;
  double u = 0.0;
  double v = 0.0;
  double r = 0.0;
  double nx = 0.0;
  double ny = 0.0;
};

const ScenarioSpec & SpecAt(int index)
{
  static const ScenarioSpec kSpecs[kScenarioCount] = {
    {"straight", false, 0.0, false},
    {"arc", true, 0.0, false},
    {"arc_cross_pi", true, M_PI - 0.02, false},
    {"straight_anchor_offset", false, 0.0, true},
  };
  return kSpecs[index];
}

CurvePoint Evaluate(const ScenarioSpec & spec, double t)
{
  CurvePoint point;
  if (!spec.arc) {
    point.x = 0.8 * t;
    point.y = 0.0;
    point.psi = 0.0;
    point.u = 0.8;
    point.v = 0.0;
    point.r = 0.0;
    point.nx = 0.0;
    point.ny = 1.0;
  } else {
    const double theta = 0.15 * t;
    point.x = 4.0 * std::sin(theta);
    point.y = 4.0 * (1.0 - std::cos(theta));
    point.psi = theta;
    point.u = 0.6;
    point.v = 0.0;
    point.r = 0.15;
    point.nx = -std::sin(theta);
    point.ny = std::cos(theta);
  }
  if (spec.rotation != 0.0) {
    const double c = std::cos(spec.rotation);
    const double s = std::sin(spec.rotation);
    const double x = point.x * c - point.y * s;
    const double y = point.x * s + point.y * c;
    const double nx = point.nx * c - point.ny * s;
    const double ny = point.nx * s + point.ny * c;
    point.x = x;
    point.y = y;
    point.nx = nx;
    point.ny = ny;
    point.psi += spec.rotation;
  }
  point.psi = WrapPi(point.psi);
  return point;
}

struct StepInput
{
  Eigen::Matrix<double, 6, 1> measured = Eigen::Matrix<double, 6, 1>::Zero();
  Eigen::MatrixXd reference;   // 6 x (N+1)
  Eigen::Vector2d anchor = Eigen::Vector2d::Zero();
};

StepInput BuildInput(
  const ScenarioSpec & spec, double t, int prediction_steps, double dt)
{
  StepInput input;
  const CurvePoint now = Evaluate(spec, t);
  input.measured << now.x + kMeasurementOffsetM * now.nx,
    now.y + kMeasurementOffsetM * now.ny, now.psi, now.u, now.v, now.r;
  input.reference = Eigen::MatrixXd::Zero(6, prediction_steps + 1);
  for (int k = 0; k <= prediction_steps; ++k) {
    const CurvePoint point = Evaluate(spec, t + k * dt);
    input.reference(0, k) = point.x;
    input.reference(1, k) = point.y;
    input.reference(2, k) = point.psi;
    input.reference(3, k) = point.u;
    input.reference(4, k) = point.v;
    input.reference(5, k) = point.r;
  }
  if (spec.custom_anchor) {
    input.anchor << kAnchorOffsetLeftN, kAnchorOffsetRightN;
  } else {
    input.anchor << kAnchorNominalN, kAnchorNominalN;
  }
  return input;
}

json MatrixJson(const Eigen::MatrixXd & matrix)
{
  json rows = json::array();
  for (int r = 0; r < matrix.rows(); ++r) {
    json row = json::array();
    for (int c = 0; c < matrix.cols(); ++c) {
      row.push_back(matrix(r, c));
    }
    rows.push_back(row);
  }
  return rows;
}

json VectorJson(const Eigen::VectorXd & vector)
{
  json values = json::array();
  for (int i = 0; i < vector.size(); ++i) {
    values.push_back(vector(i));
  }
  return values;
}

json InputJson(const StepInput & input)
{
  json out;
  out["measured"] = VectorJson(input.measured);
  out["reference"] = MatrixJson(input.reference);
  out["anchor"] = VectorJson(input.anchor);
  return out;
}

// ── 命令行 ──────────────────────────────────────────────────────────
struct Options
{
  std::string params_path;
  std::string vehicle_path;
  std::string backend;
  std::string phase;
  std::string output_path;
  /// 旧 numerical.json (逐拍重放输入), 为空表示普通场景链模式。
  std::string replay_path;
};

std::map<std::string, std::string> ParseArgs(int argc, char ** argv)
{
  std::map<std::string, std::string> args;
  for (int i = 1; i < argc; ++i) {
    std::string key = argv[i];
    if (key.rfind("--", 0) != 0) {
      Fail("无法识别的参数: " + key);
    }
    if (i + 1 >= argc) {
      Fail("参数缺少取值: " + key);
    }
    key = key.substr(2);
    if (args.count(key) != 0) {
      Fail("参数重复: " + key);
    }
    args[key] = argv[++i];
  }
  return args;
}

std::string Require(
  const std::map<std::string, std::string> & args, const std::string & key)
{
  const auto it = args.find(key);
  if (it == args.end()) {
    Fail("缺少必需参数 --" + key);
  }
  return it->second;
}

Options ParseOptions(int argc, char ** argv)
{
  const std::map<std::string, std::string> args = ParseArgs(argc, argv);
  Options options;
  options.params_path = Require(args, "params");
  options.vehicle_path = Require(args, "vehicle");
  options.backend = Require(args, "backend");
  options.phase = Require(args, "phase");
  options.output_path = Require(args, "output");
  const auto replay = args.find("replay-inputs");
  if (replay != args.end()) {
    options.replay_path = replay->second;
  }
  for (const auto & item : args) {
    if (item.first != "params" && item.first != "vehicle" &&
      item.first != "backend" && item.first != "phase" &&
      item.first != "output" && item.first != "replay-inputs")
    {
      Fail("未知参数: --" + item.first);
    }
  }
  if (!options.replay_path.empty() && options.phase != "numerical") {
    Fail("--replay-inputs 仅允许与 --phase numerical 一起使用");
  }
  if (options.backend != "acados") {
    Fail("方案 B 仅实现 acados 后端 (本包无 CasADi 实现), 收到: " +
      options.backend);
  }
  if (options.phase != "numerical" && options.phase != "timing") {
    Fail("phase 只能是 numerical 或 timing, 收到: " + options.phase);
  }
  std::ifstream existing(options.output_path);
  if (existing.good()) {
    Fail("输出文件已存在, 拒绝覆盖: " + options.output_path);
  }
  return options;
}

// ── 旧输入重放 (--replay-inputs) ────────────────────────────────────
// 逐场景/逐拍重放旧 numerical.json 的 measured/reference/anchor, 用于
// 算法迁移对照 (IPOPT 历史 oracle -> acados)。每拍在 solve 之前显式设定
// 记录 anchor, 且不使用自身返回控制替换它; 候选仍保留自身 warm 链。
class ReplayData
{
public:
  explicit ReplayData(const std::string & path)
  : source_(path)
  {
    std::ifstream stream(path);
    if (!stream.good()) {
      Fail("无法读取旧输入文件: " + path);
    }
    json document;
    stream >> document;
    const json scenarios = document.at("scenarios");
    if (!scenarios.is_array() || scenarios.empty()) {
      Fail("旧输入文件缺少 scenarios: " + path);
    }
    for (const auto & scenario : scenarios) {
      const std::string name = scenario.at("name").get<std::string>();
      if (entries_.count(name) != 0) {
        Fail("旧输入文件场景重复: " + name);
      }
      const json steps = scenario.at("steps");
      std::vector<StepInput> inputs;
      inputs.reserve(steps.size());
      for (const auto & step : steps) {
        if (!step.contains("input")) {
          Fail("旧输入文件场景 " + name + " 存在未记录 input 的拍");
        }
        const json & recorded = step.at("input");
        StepInput input;
        const json measured = recorded.at("measured");
        if (measured.size() != 6) {
          Fail("旧输入 measured 维度不是 6: " + name);
        }
        for (int i = 0; i < 6; ++i) {
          input.measured(i) = measured.at(i).get<double>();
        }
        const json reference = recorded.at("reference");
        if (reference.size() != 6) {
          Fail("旧输入 reference 行数不是 6: " + name);
        }
        input.reference.resize(6, static_cast<int>(reference.at(0).size()));
        for (int row = 0; row < 6; ++row) {
          const json & line = reference.at(row);
          if (static_cast<int>(line.size()) != input.reference.cols()) {
            Fail("旧输入 reference 各行长度不一致: " + name);
          }
          for (int col = 0; col < input.reference.cols(); ++col) {
            input.reference(row, col) = line.at(col).get<double>();
          }
        }
        const json anchor = recorded.at("anchor");
        if (anchor.size() != 2) {
          Fail("旧输入 anchor 维度不是 2: " + name);
        }
        input.anchor << anchor.at(0).get<double>(), anchor.at(1).get<double>();
        if (!input.measured.allFinite() || !input.reference.allFinite() ||
          !input.anchor.allFinite())
        {
          Fail("旧输入包含非有限值: " + name);
        }
        inputs.push_back(input);
      }
      entries_[name] = inputs;
    }
  }

  const std::string & source() const {return source_;}

  int scenario_count() const {return static_cast<int>(entries_.size());}

  const std::vector<StepInput> & At(const std::string & name) const
  {
    const auto it = entries_.find(name);
    if (it == entries_.end()) {
      Fail("旧输入文件缺少场景: " + name);
    }
    return it->second;
  }

private:
  std::string source_;
  std::map<std::string, std::vector<StepInput>> entries_;
};

// ── 参数映射 (逐行对齐 MpcControllerNode::init_mpc_solver_) ─────────
struct LoadedParams
{
  usv_mpc::MpcParams params;
  double max_solve_time_ms = 0.0;
  double horizon_budget_s = 0.0;
};

LoadedParams LoadParams(const Options & options)
{
  ParamStore store({options.params_path, options.vehicle_path});
  LoadedParams loaded;
  usv_mpc::MpcParams & p = loaded.params;

  p.dt = store.AsDouble("dynamic.dt");
  const double prediction_time =
    static_cast<double>(store.AsInt("horizon")) * store.AsDouble("mpc_dt");
  p.N = std::max(1, static_cast<int>(std::round(prediction_time / p.dt)));

  const std::vector<double> q = store.AsDoubleArray("dynamic.Q");
  const std::vector<double> r = store.AsDoubleArray("dynamic.R");
  const std::vector<double> rd = store.AsDoubleArray("dynamic.Rd");
  if (q.size() < 6 || r.size() < 2 || rd.size() < 2) {
    Fail("dynamic.Q/R/Rd 数组长度不足");
  }
  for (int i = 0; i < 6; ++i) {
    p.Q_diag(i) = q[i];
  }
  p.R_diag << r[0], r[1];
  p.Rd_diag << rd[0], rd[1];
  p.Qf_scale = store.AsDouble("dynamic.Qf_scale");
  p.T_max = store.AsDouble("dynamic.T_max");
  p.T_min = store.AsDouble("dynamic.T_min");
  p.dT_max = store.AsDouble("dynamic.dT_max");

  p.hydro.mass = store.AsDouble("vehicle.mass");
  p.hydro.Iz = store.AsDouble("vehicle.Iz");
  p.hydro.xg = store.AsDouble("vehicle.xg");
  p.hydro.d_thruster = store.AsDouble("vehicle.d_thruster");
  p.hydro.Xu_dot = store.AsDouble("vehicle.Xu_dot");
  p.hydro.Yv_dot = store.AsDouble("vehicle.Yv_dot");
  p.hydro.Yr_dot = store.AsDouble("vehicle.Yr_dot");
  p.hydro.Nv_dot = store.AsDouble("vehicle.Nv_dot");
  p.hydro.Nr_dot = store.AsDouble("vehicle.Nr_dot");
  p.hydro.Xu = store.AsDouble("vehicle.Xu");
  p.hydro.Yv = store.AsDouble("vehicle.Yv");
  p.hydro.Yr = store.AsDouble("vehicle.Yr");
  p.hydro.Nv = store.AsDouble("vehicle.Nv");
  p.hydro.Nr = store.AsDouble("vehicle.Nr");
  p.hydro.Xuu = store.AsDouble("vehicle.Xuu");
  p.hydro.Yvv = store.AsDouble("vehicle.Yvv");
  p.hydro.Yrr = store.AsDouble("vehicle.Yrr");
  p.hydro.Nvv = store.AsDouble("vehicle.Nvv");
  p.hydro.Nrr = store.AsDouble("vehicle.Nrr");

  loaded.max_solve_time_ms = store.AsDouble("max_solve_time_ms");
  loaded.horizon_budget_s = prediction_time;
  return loaded;
}

json ParamsJson(const LoadedParams & loaded)
{
  const usv_mpc::MpcParams & p = loaded.params;
  json out;
  out["dt"] = p.dt;
  out["N"] = p.N;
  out["Q"] = VectorJson(p.Q_diag);
  out["R"] = VectorJson(p.R_diag);
  out["Rd"] = VectorJson(p.Rd_diag);
  out["Qf_scale"] = p.Qf_scale;
  out["T_max"] = p.T_max;
  out["T_min"] = p.T_min;
  out["dT_max"] = p.dT_max;
  out["horizon_budget_s"] = loaded.horizon_budget_s;
  out["max_solve_time_ms"] = loaded.max_solve_time_ms;
  json hydro;
  hydro["mass"] = p.hydro.mass;
  hydro["Iz"] = p.hydro.Iz;
  hydro["xg"] = p.hydro.xg;
  hydro["d_thruster"] = p.hydro.d_thruster;
  hydro["Xu_dot"] = p.hydro.Xu_dot;
  hydro["Yv_dot"] = p.hydro.Yv_dot;
  hydro["Yr_dot"] = p.hydro.Yr_dot;
  hydro["Nv_dot"] = p.hydro.Nv_dot;
  hydro["Nr_dot"] = p.hydro.Nr_dot;
  hydro["Xu"] = p.hydro.Xu;
  hydro["Yv"] = p.hydro.Yv;
  hydro["Yr"] = p.hydro.Yr;
  hydro["Nv"] = p.hydro.Nv;
  hydro["Nr"] = p.hydro.Nr;
  hydro["Xuu"] = p.hydro.Xuu;
  hydro["Yvv"] = p.hydro.Yvv;
  hydro["Yrr"] = p.hydro.Yrr;
  hydro["Nvv"] = p.hydro.Nvv;
  hydro["Nrr"] = p.hydro.Nrr;
  out["hydro"] = hydro;
  return out;
}

// ── 单拍记录 ────────────────────────────────────────────────────────
struct StepRecord
{
  bool has_input = false;
  StepInput input;
  std::string anchor_source = "";
  bool success = false;
  std::string error;
  std::string backend;
  double wall_ms = 0.0;
  double reported_ms = 0.0;
  Eigen::Vector2d control = Eigen::Vector2d::Zero();
  Eigen::MatrixXd x_pred;
  Eigen::MatrixXd u_pred;
  double bound_violation = 0.0;
  double rate_violation = 0.0;
};

/// 控制边界与推力增量约束的最大越界量 (由预测控制序列复核)。
void AuditConstraints(const usv_mpc::MpcParams & params, StepRecord & record)
{
  record.bound_violation = 0.0;
  record.rate_violation = 0.0;
  if (record.u_pred.rows() != 2) {
    return;
  }
  const double rate_step = params.dT_max * params.dt;
  Eigen::Vector2d previous = record.input.anchor;
  for (int k = 0; k < record.u_pred.cols(); ++k) {
    const Eigen::Vector2d u = record.u_pred.col(k);
    record.bound_violation = std::max(
      {record.bound_violation, params.T_min - u(0), u(0) - params.T_max,
        params.T_min - u(1), u(1) - params.T_max});
    record.rate_violation = std::max(
      {record.rate_violation, std::fabs(u(0) - previous(0)) - rate_step,
        std::fabs(u(1) - previous(1)) - rate_step});
    previous = u;
  }
}

json StepJson(const StepRecord & record, bool with_solution)
{
  json out;
  if (record.has_input) {
    out["input"] = InputJson(record.input);
  }
  if (!record.anchor_source.empty()) {
    out["anchor_source"] = record.anchor_source;
  }
  out["success"] = record.success;
  out["backend"] = record.backend;
  out["wall_ms"] = record.wall_ms;
  out["reported_ms"] = record.reported_ms;
  out["control"] = VectorJson(record.control);
  if (!record.error.empty()) {
    out["error"] = record.error;
  }
  if (with_solution && record.success) {
    out["X"] = MatrixJson(record.x_pred);
    out["U"] = MatrixJson(record.u_pred);
    out["bound_violation"] = record.bound_violation;
    out["rate_violation"] = record.rate_violation;
  }
  return out;
}

struct ScenarioResult
{
  std::string name;
  double cold_start_us = 0.0;
  double first_solve_ms = 0.0;
  std::vector<StepRecord> steps;
};

ScenarioResult RunScenario(
  int index, const Options & options, const LoadedParams & loaded,
  const ReplayData * replay)
{
  const ScenarioSpec & spec = SpecAt(index);
  const usv_mpc::MpcParams & params = loaded.params;
  const bool numerical = (options.phase == "numerical");
  int total_steps = numerical ? kNumericalSteps :
    (kTimingWarmup + kTimingMeasured);
  if (replay != nullptr) {
    const auto & recorded = replay->At(spec.name);
    if (static_cast<int>(recorded.size()) < kNumericalSteps) {
      Fail("旧输入场景 " + std::string(spec.name) + " 拍数不足");
    }
    total_steps = kNumericalSteps;
  }

  ScenarioResult result;
  result.name = spec.name;

  const auto construct_begin = std::chrono::steady_clock::now();
  // 显式构造 acados 后端 (不经工厂的其它后端分支)。
  std::unique_ptr<usv_mpc::DynamicMpc> solver =
    std::make_unique<usv_mpc::AcadosBackend>(params);
  const auto construct_end = std::chrono::steady_clock::now();
  result.cold_start_us =
    std::chrono::duration<double, std::micro>(construct_end - construct_begin).count();

  result.steps.resize(total_steps);
  // 求解器本拍真正收到的推力锚点: 首拍取场景锚点, 之后取上一拍实际下发指令。
  Eigen::Vector2d effective_anchor = Eigen::Vector2d::Zero();
  for (int i = 0; i < total_steps; ++i) {
    StepRecord & record = result.steps[i];
    // 场景是解析给定的: 每拍输入只由时刻 i*dt 决定, 不从求解输出推进状态。
    // 输入构造在计时区外完成。
    const StepInput input = (replay != nullptr) ?
      replay->At(spec.name).at(static_cast<size_t>(i)) :
      BuildInput(spec, i * params.dt, params.N, params.dt);
    const bool sampled = numerical ||
      std::count(kSampledInputSteps.begin(), kSampledInputSteps.end(), i) > 0;

    // 锚点: 场景规定的推力锚点必须在**首拍求解前**送入求解器 —— 否则第 4 场景
    // 的 [5,-5] 根本没被使用, delta_T 约束也从 0 起算。后续各拍沿用上一拍实际
    // 下发指令, 保持真实热启动链。anchor_source 逐拍记录来源。
    // 重放模式下每拍都用记录锚点, 且绝不用自身返回控制替换它 (否则输入不同源)。
    if (replay != nullptr) {
      effective_anchor = input.anchor;
      solver->set_applied_control(input.anchor);
      record.anchor_source = "replay";
    } else if (i == 0) {
      effective_anchor = input.anchor;
      solver->set_applied_control(input.anchor);
      record.anchor_source = "scenario";
    } else {
      record.anchor_source = "solver_return";
    }
    if (sampled) {
      record.has_input = true;
      record.input = input;
      // 记录该拍求解器实际使用的锚点, 便于事后核对非零锚点确实被送入。
      record.input.anchor = effective_anchor;
    }

    const auto begin = std::chrono::steady_clock::now();
    const std::pair<Eigen::Vector2d, usv_mpc::SolveInfo> result_pair =
      solver->solve(input.measured, input.reference);
    const auto end = std::chrono::steady_clock::now();

    record.wall_ms = std::chrono::duration<double, std::milli>(end - begin).count();
    record.reported_ms = result_pair.second.solve_time_ms;
    record.success = result_pair.second.success;
    record.error = result_pair.second.error;
    record.backend = result_pair.second.backend;
    record.control = result_pair.first;
    record.x_pred = result_pair.second.X_pred;
    record.u_pred = result_pair.second.U_pred;
    if (record.success) {
      // 约束复核需要本拍锚点: 未采样拍临时填写, 复核后恢复。
      const bool restore_input = !sampled;
      if (restore_input) {
        record.input = input;
        record.has_input = true;
        record.input.anchor = effective_anchor;
      }
      record.bound_violation = 0.0;
      record.rate_violation = 0.0;
      if (record.x_pred.allFinite() && record.u_pred.allFinite()) {
        AuditConstraints(params, record);
      } else {
        record.success = false;
        record.error = "non_finite_output";
      }
      if (restore_input) {
        record.has_input = false;
        record.input = StepInput();
      }
    }

    if (i == 0) {
      result.first_solve_ms = record.wall_ms;
    }
    if (record.backend != "acados") {
      Fail("后端标识不是 acados, 求解器实际后端: " + record.backend);
    }
    // 与节点一致: 把本轮实际下发指令写回下一拍推力增量锚点 (热启动链)。
    // 重放模式保留记录锚点, 不把自身返回控制写回。
    if (replay == nullptr) {
      solver->set_applied_control(record.control);
      effective_anchor = record.control;
    }
  }
  return result;
}

bool AnyFailure(const std::vector<ScenarioResult> & results)
{
  for (const auto & scenario : results) {
    for (const auto & step : scenario.steps) {
      if (!step.success) {
        return true;
      }
    }
  }
  return false;
}

}  // namespace

int main(int argc, char ** argv)
{
  try {
    const Options options = ParseOptions(argc, argv);
    const LoadedParams loaded = LoadParams(options);

    std::unique_ptr<ReplayData> replay;
    if (!options.replay_path.empty()) {
      replay = std::make_unique<ReplayData>(options.replay_path);
      for (int i = 0; i < kScenarioCount; ++i) {
        replay->At(SpecAt(i).name);  // 缺场景在此失败, 不进入求解
      }
      if (replay->scenario_count() != kScenarioCount) {
        Fail("旧输入场景数与固定场景集不一致: " +
             std::to_string(replay->scenario_count()));
      }
    }

    std::vector<ScenarioResult> results;
    results.reserve(kScenarioCount);
    for (int i = 0; i < kScenarioCount; ++i) {
      results.push_back(RunScenario(i, options, loaded, replay.get()));
    }

    json scenarios = json::array();
    for (const auto & scenario : results) {
      json steps = json::array();
      const bool with_solution = (options.phase == "numerical");
      for (const auto & step : scenario.steps) {
        steps.push_back(StepJson(step, with_solution));
      }
      json entry;
      entry["name"] = scenario.name;
      entry["cold_start_us"] = scenario.cold_start_us;
      entry["first_solve_ms"] = scenario.first_solve_ms;
      entry["steps"] = steps;
      scenarios.push_back(entry);
    }

    json document;
    document["program"] = "benchmark_dynamic_solver";
    document["package"] = "usv_nmpc";
    document["phase"] = options.phase;
    document["backend"] = options.backend;
    document["yaml_files"] = json::array(
      {options.params_path, options.vehicle_path});
    document["solver_params"] = ParamsJson(loaded);
    document["timing_warmup"] = kTimingWarmup;
    document["timing_measured"] = kTimingMeasured;
    document["numerical_steps"] = kNumericalSteps;
    if (replay != nullptr) {
      document["replay"] = {{"source", replay->source()}};
    }
    document["scenarios"] = scenarios;

    std::ofstream out(options.output_path);
    if (!out.good()) {
      Fail("无法写入输出文件: " + options.output_path);
    }
    out << document.dump(2) << "\n";
    out.close();

    const bool failed = AnyFailure(results);
    std::printf(
      "usv_nmpc phase=%s backend=%s N=%d dt=%.3f 场景=%zu 失败拍=%d\n",
      options.phase.c_str(), options.backend.c_str(), loaded.params.N,
      loaded.params.dt, results.size(), failed ? 1 : 0);
    if (options.phase == "numerical" && failed) {
      std::fprintf(stderr, "数值阶段存在未成功求解的拍, 判定失败\n");
      return 1;
    }
    return 0;
  } catch (const std::exception & error) {
    std::fprintf(stderr, "错误: %s\n", error.what());
    return 2;
  }
}
