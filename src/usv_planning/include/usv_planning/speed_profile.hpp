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
 * @file speed_profile.hpp
 * @brief 速度/时间层：时间最优速度剖面 TOPP。
 */

#pragma once

#include <Eigen/Dense>

namespace usv_planning {

/// compute_profile 的输出结果。
struct ProfileResult {
  Eigen::VectorXd vs;   // 每点速度 (m/s)
  Eigen::VectorXd rs;   // 参考转艏角速度 = kappa*v (rad/s)
  Eigen::VectorXd ts;   // 每点时间戳 (s)
};

/**
 * @brief 计算时间最优速度剖面（确定性两遍扫描，O(N)，<1ms）。
 *
 * @param kappas     每点曲率 (1/m)
 * @param s          累积弧长 (m)
 * @param u_max      最大巡航速度 (m/s)
 * @param r_max      最大转艏角速度 (rad/s)
 * @param a_lat_max  最大侧向加速度 (m/s²)
 * @param a_acc      最大纵向加速度 (m/s²)
 * @param a_dec      最大纵向减速度 (m/s²)
 * @param v_start    起点速度 (m/s)
 * @param v_end      末端目标速度 (m/s)
 * @param v_min      最小速度下限，保证时间推进 (m/s)
 * @return 速度剖面计算结果 ProfileResult
 */
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
    double v_min = 0.2);

}  // 命名空间 usv_planning
