// 版权所有 2026 USV Developer
//
// 特此免费授予任何获得本软件及相关文档文件（下称“软件”）副本的人不受限制地处置该软件的权利，
// 包括但不限于使用、复制、修改、合并、发布、分发、再许可和/或出售软件副本的权利，
// 以及允许获得本软件的人这样做，但须满足以下条件：
//
// 上述版权声明和本许可声明应包含在软件的所有副本或主要部分中。
//
// 本软件按“原样”提供，不附带任何明示或暗示的担保，包括但不限于对适销性、
// 特定用途适用性和非侵权性的担保。在任何情况下，作者或版权持有人均不对因软件、
// 软件的使用或与软件相关的其他交易而产生的任何索赔、损害赔偿或其他责任承担责任，
// 无论该等责任是基于合同诉讼、侵权行为还是其他原因。


/**
 * @file speed_profile.cpp
 * @brief 时间最优速度剖面 TOPP 实现（基于 Eigen）。
 *
 * 确定性两遍扫描，O(N)，<1ms，无实时性风险。
 */

#include "usv_planning/speed_profile.hpp"

#include <algorithm>
#include <cmath>

namespace usv_planning {

static constexpr double EPS = 1e-6;

ProfileResult compute_profile(
    const Eigen::VectorXd& kappas,
    const Eigen::VectorXd& s,
    double u_max,
    double r_max,
    double a_lat_max,
    double a_acc,
    double a_dec,
    double v_start,
    double v_end,
    double v_min) {
  const int n = static_cast<int>(s.size());
  ProfileResult result;

  if (n == 0) {
    return result;
  }
  if (n == 1) {
    result.vs = Eigen::VectorXd::Constant(1, std::max(v_min, 0.0));
    result.rs = Eigen::VectorXd::Zero(1);
    result.ts = Eigen::VectorXd::Zero(1);
    return result;
  }

  // 参数下限保护
  u_max     = std::max(EPS, u_max);
  a_lat_max = std::max(EPS, a_lat_max);
  a_acc     = std::max(EPS, a_acc);
  a_dec     = std::max(EPS, a_dec);

  Eigen::VectorXd kappa_abs = kappas.array().abs();

  // ── 曲率限速包络 ──
  Eigen::VectorXd v_curve = Eigen::VectorXd::Constant(n, u_max);
  for (int i = 0; i < n; ++i) {
    if (kappa_abs(i) > EPS) {
      double v_turn = r_max / kappa_abs(i);
      double v_lat  = std::sqrt(a_lat_max / kappa_abs(i));
      v_curve(i) = std::min({v_curve(i), v_turn, v_lat});
    }
  }
  v_curve = v_curve.cwiseMax(0.0);

  Eigen::VectorXd v = v_curve;

  // 起点速度（受当前速度与曲率限速共同约束）
  v(0) = std::min(v_curve(0), std::max(v_start, 0.0));

  // ── 前向扫描：受加速度上限 a_acc 约束 ──
  for (int i = 1; i < n; ++i) {
    double ds = std::max(EPS, s(i) - s(i - 1));
    v(i) = std::min(v_curve(i),
                    std::sqrt(v(i - 1) * v(i - 1) + 2.0 * a_acc * ds));
  }

  // 末端速度
  v(n - 1) = std::min(v(n - 1), std::max(v_end, 0.0));

  // ── 后向扫描：受减速度上限 a_dec 约束 ──
  for (int i = n - 2; i >= 0; --i) {
    double ds = std::max(EPS, s(i + 1) - s(i));
    v(i) = std::min(v(i),
                    std::sqrt(v(i + 1) * v(i + 1) + 2.0 * a_dec * ds));
  }

  // ── 时间积分（梯形） ──
  Eigen::VectorXd ts = Eigen::VectorXd::Zero(n);
  for (int i = 1; i < n; ++i) {
    double ds    = s(i) - s(i - 1);
    double v_avg = std::max(0.5 * (v(i - 1) + v(i)), v_min);
    ts(i) = ts(i - 1) + ds / v_avg;
  }

  // 参考转艏角速度 rs = kappas * v
  Eigen::VectorXd rs = kappas.array() * v.array();

  result.vs = std::move(v);
  result.rs = std::move(rs);
  result.ts = std::move(ts);
  return result;
}

}  // 命名空间 usv_planning
