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
 * @brief 运动学 MPC (方案 A) 固定输入数值/耗时/闭环基线诊断程序。
 *
 * 仅用于同一冻结源码的 NoOpt 与 Release 两套构建离线对照, 不安装、不参与
 * 生产控制链路, 默认不构建 (需 -DUSV_BUILD_BASELINE_BENCHMARK=ON)。
 *
 * 参数一律从部署期 mpc_params_A.yaml / usv_params_A.yaml 读取 (与节点
 * init_mpc_solver_() 同一套字段映射), 不创建 ROS 通信节点, 不写参数服务,
 * 不使用结构体默认值替代冻结 YAML。
 *
 * 三个 phase:
 *   numerical   4 场景 x 5 拍, 输出完整 X/U + 四残差 + objective/acados_cost
 *   timing      4 场景 x (20 预热 + 500 计时), 只调用完整 facade solve
 *   closed_loop 4 场景 x 200 拍, 用本拍实际输出命令推进独立 plant, 汇总 RMSE
 *
 * 用法:
 *   benchmark_kinematic_solver --params <mpc_params_A.yaml>
 *     --vehicle <usv_params_A.yaml> --backend acados
 *     --phase numerical|timing|closed_loop --output <新的 JSON 路径>
 *
 *   # 逐拍重放旧 numerical.json 的 measured/reference/anchor (仅 numerical)
 *   benchmark_kinematic_solver ... --phase numerical \
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
#include <rclcpp/parameter_value.hpp>

#include "usv_mpc/acados_kinematic_backend.hpp"
#include "usv_mpc/kinematic_mpc_solver.hpp"
#include "usv_mpc/usv_model_kinematic.hpp"

namespace
{

using json = nlohmann::json;

/// 场景数量: 直线 / 圆弧 / 跨 ±π 圆弧 / 直线+非零锚点。
constexpr int kScenarioCount = 4;
/// 计时阶段的预热拍数与计时拍数 (计划固定值, 不提供调参入口)。
constexpr int kTimingWarmup = 20;
constexpr int kTimingMeasured = 500;
/// 数值阶段的每场景拍数 (含完整热启动链)。
constexpr int kNumericalSteps = 5;
/// 闭环阶段的每场景拍数。
constexpr int kClosedLoopSteps = 200;
/// 测量位置沿曲线法向的固定偏移 (m)。
constexpr double kMeasurementOffsetM = 0.2;
/// 计时阶段采样记录的输入拍号 (其余拍只记输出, 避免 JSON 过大)。
const std::vector<int> kSampledInputSteps = {0, 64, 128, 256, 384, 511};

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
class ParamStore
{
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

  /// 读取 YAML 中缺失的键时回落到节点 declare_parameter 的默认值, 并把回落
  /// 记录在案 (defaulted_params), 不静默替换冻结参数。
  double AsDoubleOrDefault(const std::string & name, double fallback)
  {
    if (values_.find(name) == values_.end()) {
      defaulted_.push_back(name);
      return fallback;
    }
    return values_.at(name).as_double();
  }

  const std::vector<std::string> & defaulted() const {return defaulted_;}

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
  std::vector<std::string> defaulted_;
};

// ── 固定输入场景 ────────────────────────────────────────────────────
struct ScenarioSpec
{
  const char * name;
  bool arc;              // true: 圆弧; false: 直线
  double rotation;       // 整体旋转角 (跨 ±π 场景)
  bool custom_anchor;    // true: 使用非零固定锚点
};

struct CurvePoint
{
  double x = 0.0;
  double y = 0.0;
  double psi = 0.0;
  double u = 0.0;
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
    point.r = 0.0;
    point.nx = 0.0;
    point.ny = 1.0;
  } else {
    const double theta = 0.15 * t;
    point.x = 4.0 * std::sin(theta);
    point.y = 4.0 * (1.0 - std::cos(theta));
    point.psi = theta;
    point.u = 0.6;
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
  Eigen::Matrix<double, 5, 1> measured = Eigen::Matrix<double, 5, 1>::Zero();
  Eigen::MatrixXd reference;   // 3 x (N+1)
  Eigen::Vector2d anchor = Eigen::Vector2d::Zero();
};

StepInput BuildInput(
  const ScenarioSpec & spec, double t, int prediction_steps, double dt)
{
  StepInput input;
  const CurvePoint now = Evaluate(spec, t);
  input.measured << now.x + kMeasurementOffsetM * now.nx,
    now.y + kMeasurementOffsetM * now.ny, now.psi, now.u, now.r;
  input.reference = Eigen::MatrixXd::Zero(3, prediction_steps + 1);
  for (int k = 0; k <= prediction_steps; ++k) {
    const CurvePoint point = Evaluate(spec, t + k * dt);
    input.reference(0, k) = point.x;
    input.reference(1, k) = point.y;
    input.reference(2, k) = point.psi;
  }
  if (spec.custom_anchor) {
    input.anchor << 0.4, 0.1;
  } else {
    input.anchor << now.u, now.r;
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
  if (options.backend != "acados") {
    Fail("方案 A 仅实现 acados 后端, 收到: " + options.backend);
  }
  if (options.phase != "numerical" && options.phase != "timing" &&
    options.phase != "closed_loop")
  {
    Fail("phase 只能是 numerical/timing/closed_loop, 收到: " + options.phase);
  }
  if (!options.replay_path.empty() && options.phase != "numerical") {
    Fail("--replay-inputs 仅允许与 --phase numerical 一起使用");
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
        if (measured.size() != 5) {
          Fail("旧输入 measured 维度不是 5: " + name);
        }
        for (int i = 0; i < 5; ++i) {
          input.measured(i) = measured.at(i).get<double>();
        }
        const json reference = recorded.at("reference");
        if (reference.size() != 3) {
          Fail("旧输入 reference 行数不是 3: " + name);
        }
        input.reference.resize(3, static_cast<int>(reference.at(0).size()));
        for (int row = 0; row < 3; ++row) {
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
  usv_mpc::KinematicMpcParams params;
  double max_solve_time_ms = 0.0;
  double horizon_budget_s = 0.0;
  std::vector<std::string> defaulted;
};

LoadedParams LoadParams(const Options & options)
{
  ParamStore store({options.params_path, options.vehicle_path});
  LoadedParams loaded;
  usv_mpc::KinematicMpcParams & p = loaded.params;

  // mpc_params_A.yaml 现在显式声明 kinematic.dt; 缺省时回落节点默认值并记录。
  p.dt = store.AsDoubleOrDefault("kinematic.dt", 0.2);
  const double prediction_time =
    static_cast<double>(store.AsInt("horizon")) * store.AsDouble("mpc_dt");
  p.N = std::max(1, static_cast<int>(std::round(prediction_time / p.dt)));

  const std::vector<double> q = store.AsDoubleArray("kinematic.Q");
  const std::vector<double> r = store.AsDoubleArray("kinematic.R");
  if (q.size() < 3 || r.size() < 2) {
    Fail("kinematic.Q/R 数组长度不足");
  }
  for (int i = 0; i < 3; ++i) {
    p.Q_diag(i) = q[i];
  }
  p.R_diag << r[0], r[1];
  p.Qf_scale = store.AsDouble("kinematic.Qf_scale");
  p.u_max = store.AsDouble("kinematic.u_max");
  p.u_min = store.AsDouble("kinematic.u_min");
  p.r_max = store.AsDouble("kinematic.r_max");
  p.du_max = store.AsDouble("kinematic.du_max");
  p.dr_max = store.AsDouble("kinematic.dr_max");
  p.tau_u = store.AsDouble("kinematic.tau_u");
  p.tau_r = store.AsDouble("kinematic.tau_r");
  p.solution_constraint_tol = store.AsDouble("kinematic.solution_constraint_tol");

  loaded.max_solve_time_ms = store.AsDouble("max_solve_time_ms");
  loaded.horizon_budget_s = prediction_time;
  loaded.defaulted = store.defaulted();
  return loaded;
}

json ParamsJson(const LoadedParams & loaded)
{
  const usv_mpc::KinematicMpcParams & p = loaded.params;
  json out;
  out["dt"] = p.dt;
  out["N"] = p.N;
  out["Q"] = VectorJson(p.Q_diag);
  out["R"] = VectorJson(p.R_diag);
  out["Qf_scale"] = p.Qf_scale;
  out["u_max"] = p.u_max;
  out["u_min"] = p.u_min;
  out["r_max"] = p.r_max;
  out["du_max"] = p.du_max;
  out["dr_max"] = p.dr_max;
  out["tau_u"] = p.tau_u;
  out["tau_r"] = p.tau_r;
  out["solution_constraint_tol"] = p.solution_constraint_tol;
  out["horizon_budget_s"] = loaded.horizon_budget_s;
  out["max_solve_time_ms"] = loaded.max_solve_time_ms;
  out["defaulted_params"] = loaded.defaulted;
  return out;
}

/// 原解析目标 J (与 IPOPT 时期的 CasADi 目标逐项一致, 不乘 dt)。
///   sum_{k<N} [Qx*ex² + Qy*ey² + 2*Qpsi*(1-cos) + Ru*uc² + Rr*rc²]
///   + Qf_scale*[Qx*exN² + Qy*eyN² + 2*Qpsi*(1-cos_N)]
double AnalyticObjective(
  const usv_mpc::KinematicMpcParams & params,
  const Eigen::MatrixXd & X,
  const Eigen::MatrixXd & U,
  const Eigen::MatrixXd & reference)
{
  const int N = params.N;
  const double qx = params.Q_diag(0), qy = params.Q_diag(1), qpsi = params.Q_diag(2);
  const double ru = params.R_diag(0), rr = params.R_diag(1);
  double cost = 0.0;
  for (int k = 0; k < N; ++k) {
    const double ex = X(0, k) - reference(0, k);
    const double ey = X(1, k) - reference(1, k);
    const double epsi = X(2, k) - reference(2, k);
    cost += qx * ex * ex + qy * ey * ey +
      2.0 * qpsi * (1.0 - std::cos(epsi));
    cost += ru * U(0, k) * U(0, k) + rr * U(1, k) * U(1, k);
  }
  const double exN = X(0, N) - reference(0, N);
  const double eyN = X(1, N) - reference(1, N);
  const double epsiN = X(2, N) - reference(2, N);
  cost += params.Qf_scale * (qx * exN * exN + qy * eyN * eyN +
    2.0 * qpsi * (1.0 - std::cos(epsiN)));
  return cost;
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
  double initial_state_residual = 0.0;
  double dynamics_residual = 0.0;
  double bound_violation = 0.0;
  double rate_violation = 0.0;
  bool has_cost = false;
  double objective = 0.0;
  double acados_cost = 0.0;
};

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
    out["initial_state_residual"] = record.initial_state_residual;
    out["dynamics_residual"] = record.dynamics_residual;
    out["bound_violation"] = record.bound_violation;
    out["rate_violation"] = record.rate_violation;
  }
  if (record.has_cost) {
    out["objective"] = record.objective;
    out["acados_cost"] = record.acados_cost;
  }
  return out;
}

struct ScenarioResult
{
  std::string name;
  double cold_start_us = 0.0;
  double first_solve_ms = 0.0;
  std::vector<StepRecord> steps;
  // closed_loop 专用: 逐拍 plant/reference/命令, 供比较器独立重算 RMSE。
  std::vector<Eigen::Matrix<double, 5, 1>> plant;
  std::vector<Eigen::Matrix<double, 3, 1>> reference_first;
  int closed_loop_failures = 0;
};

/// 构造一次求解器, 并在同一实例上跑完一个场景。
ScenarioResult RunScenario(
  int index, const Options & options, const LoadedParams & loaded,
  const ReplayData * replay)
{
  const ScenarioSpec & spec = SpecAt(index);
  const usv_mpc::KinematicMpcParams & params = loaded.params;
  const bool numerical = (options.phase == "numerical");
  const bool closed_loop = (options.phase == "closed_loop");
  int total_steps = numerical ? kNumericalSteps :
    (closed_loop ? kClosedLoopSteps : (kTimingWarmup + kTimingMeasured));
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
  // 走生产工厂路径 (make_kinematic_mpc), 再向下转型取 generated cost 接口:
  // 工厂若换成别的后端, 这里必须显式失败而不是静默跳过成本门禁。
  std::unique_ptr<usv_mpc::KinematicMpc> solver =
    usv_mpc::make_kinematic_mpc(params);
  auto * concrete = dynamic_cast<usv_mpc::AcadosKinematicBackend *>(solver.get());
  if (solver == nullptr || concrete == nullptr) {
    Fail("工厂未返回 AcadosKinematicBackend, 无法读取 generated cost");
  }
  const auto construct_end = std::chrono::steady_clock::now();
  result.cold_start_us =
    std::chrono::duration<double, std::micro>(construct_end - construct_begin).count();

  // closed_loop 的独立 plant: 与求解器同 dt/同 tau 的 5 状态滞后模型。
  usv_mpc::USVKinematicModel plant(params.dt, 4);
  Eigen::Matrix<double, 5, 1> plant_state = Eigen::Matrix<double, 5, 1>::Zero();

  result.steps.resize(total_steps);
  if (closed_loop) {
    result.plant.reserve(total_steps);
    result.reference_first.reserve(total_steps);
  }
  // 求解器本拍真正收到的控制锚点。
  Eigen::Vector2d effective_anchor = Eigen::Vector2d::Zero();
  Eigen::Vector2d last_command = Eigen::Vector2d::Zero();

  for (int i = 0; i < total_steps; ++i) {
    StepRecord & record = result.steps[i];
    StepInput input;
    if (replay != nullptr) {
      input = replay->At(spec.name).at(static_cast<size_t>(i));
    } else if (closed_loop) {
      // 第 0 拍用原场景的解析状态; 之后由独立 plant 推进。
      if (i == 0) {
        const CurvePoint now = Evaluate(spec, 0.0);
        input.measured << now.x + kMeasurementOffsetM * now.nx,
          now.y + kMeasurementOffsetM * now.ny, now.psi, now.u, now.r;
        plant_state = input.measured;
      } else {
        input.measured = plant_state;
        // 求解器只看归一化后的 psi; plant 内部保持连续展开。
        input.measured(2) = WrapPi(input.measured(2));
      }
      input.reference = Eigen::MatrixXd::Zero(3, params.N + 1);
      for (int k = 0; k <= params.N; ++k) {
        const CurvePoint point = Evaluate(spec, i * params.dt + k * params.dt);
        input.reference(0, k) = point.x;
        input.reference(1, k) = point.y;
        input.reference(2, k) = point.psi;
      }
      // 首拍按原场景锚点 (与 BuildInput 的定义一致), 其后为上一拍实际输出。
      if (i == 0) {
        const CurvePoint start = Evaluate(spec, 0.0);
        if (spec.custom_anchor) {
          input.anchor << 0.4, 0.1;
        } else {
          input.anchor << start.u, start.r;
        }
      } else {
        input.anchor = effective_anchor;
      }
    } else {
      input = BuildInput(spec, i * params.dt, params.N, params.dt);
    }
    const bool sampled = numerical || closed_loop ||
      std::count(kSampledInputSteps.begin(), kSampledInputSteps.end(), i) > 0;

    // 锚点: 场景锚点必须在首拍求解前送入 (否则第 4 场景的 [0.4,0.1] 没生效,
    // 速率约束从 0 起算)。后续各拍沿用上一拍实际下发指令; closed_loop 同样。
    // replay 模式每拍都用记录锚点, 且不用自身返回控制替换它。
    if (replay != nullptr) {
      effective_anchor = input.anchor;
      solver->set_applied_command(input.anchor);
      record.anchor_source = "replay";
    } else if (i == 0) {
      effective_anchor = input.anchor;
      solver->set_applied_command(input.anchor);
      record.anchor_source = "scenario";
    } else {
      record.anchor_source = (closed_loop ? "closed_loop" : "solver_return");
    }
    if (sampled) {
      record.has_input = true;
      record.input = input;
      // 记录该拍求解器实际使用的锚点。
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
    record.initial_state_residual = result_pair.second.initial_state_residual;
    record.dynamics_residual = result_pair.second.max_dynamics_residual;
    record.bound_violation = result_pair.second.max_control_bound_violation;
    record.rate_violation = result_pair.second.max_control_rate_violation;

    // 成本语义: 成功解在 set_applied_command/下一次 solve 之前立即读取
    // generated cost, 并与独立解析目标比对 (由比较器判定阈值)。
    if (record.success && (numerical || replay != nullptr)) {
      record.objective = AnalyticObjective(params, record.x_pred, record.u_pred,
          input.reference);
      record.acados_cost = concrete->diagnostic_cost();
      record.has_cost = true;
    }

    if (i == 0) {
      result.first_solve_ms = record.wall_ms;
    }
    if (record.backend != std::string("acados")) {
      Fail("后端标识不是 acados, 求解器实际后端: " + record.backend);
    }

    if (closed_loop) {
      result.plant.push_back(plant_state);
      Eigen::Matrix<double, 3, 1> reference_first;
      reference_first << input.reference(0, 0), input.reference(1, 0),
        input.reference(2, 0);
      result.reference_first.push_back(reference_first);
      if (record.success) {
        // 只用本拍实际输出命令推进独立 plant (绝不用 X_pred.col(1) 自证)。
        plant_state = plant.forward_unwrapped(plant_state, record.control,
            params.tau_u, params.tau_r);
      } else {
        // 失败保持上一命令, 并如实计数 (不能当作成功)。
        ++result.closed_loop_failures;
        plant_state = plant.forward_unwrapped(plant_state, last_command,
            params.tau_u, params.tau_r);
      }
      last_command = record.control;
    }

    if (replay == nullptr) {
      // 与节点一致: 把本轮实际下发指令写回速率约束锚点 (热启动链)。
      solver->set_applied_command(record.control);
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
      const bool with_solution =
        (options.phase == "numerical") || (replay != nullptr);
      for (const auto & step : scenario.steps) {
        steps.push_back(StepJson(step, with_solution));
      }
      json entry;
      entry["name"] = scenario.name;
      entry["cold_start_us"] = scenario.cold_start_us;
      entry["first_solve_ms"] = scenario.first_solve_ms;
      entry["steps"] = steps;
      if (options.phase == "closed_loop") {
        json plants = json::array();
        json references = json::array();
        for (size_t i = 0; i < scenario.plant.size(); ++i) {
          plants.push_back(VectorJson(scenario.plant[i]));
          references.push_back(VectorJson(scenario.reference_first[i]));
        }
        entry["plant_states"] = plants;
        entry["reference_first_column"] = references;
        entry["closed_loop_failures"] = scenario.closed_loop_failures;
      }
      scenarios.push_back(entry);
    }

    json document;
    document["program"] = "benchmark_kinematic_solver";
    document["package"] = "usv_mpc";
    document["phase"] = options.phase;
    document["backend"] = options.backend;
    document["yaml_files"] = json::array(
      {options.params_path, options.vehicle_path});
    document["solver_params"] = ParamsJson(loaded);
    document["timing_warmup"] = kTimingWarmup;
    document["timing_measured"] = kTimingMeasured;
    document["numerical_steps"] = kNumericalSteps;
    if (options.phase == "closed_loop") {
      document["closed_loop_steps"] = kClosedLoopSteps;
    }
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
      "usv_mpc phase=%s backend=%s N=%d dt=%.3f 场景=%zu 失败拍=%d\n",
      options.phase.c_str(), options.backend.c_str(), loaded.params.N,
      loaded.params.dt, results.size(), failed ? 1 : 0);
    if ((options.phase == "numerical" || options.phase == "closed_loop") && failed) {
      std::fprintf(stderr, "阶段存在未成功求解的拍, 判定失败\n");
      return 1;
    }
    return 0;
  } catch (const std::exception & error) {
    std::fprintf(stderr, "错误: %s\n", error.what());
    return 2;
  }
}
