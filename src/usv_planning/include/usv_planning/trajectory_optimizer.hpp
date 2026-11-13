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
 * @file trajectory_optimizer.hpp
 * @brief 轨迹几何层：G1 圆弧倒角（fillet）平滑。
 */

#pragma once

#include <string>
#include <vector>

#include <Eigen/Dense>

namespace usv_planning {

/// fillet_path 的输出结果。
struct FilletResult {
  Eigen::VectorXd xs;       // 位置 x
  Eigen::VectorXd ys;       // 位置 y
  Eigen::VectorXd psis;     // 连续累积航向 (rad)
  Eigen::VectorXd kappas;   // 有符号曲率 (1/m)
  Eigen::VectorXd s;        // 累积弧长 (m)
  std::vector<std::string> warnings;
};

/// recompute_geometry 的输出结果。
struct GeometryResult {
  Eigen::VectorXd psis;
  Eigen::VectorXd kappas;
  Eigen::VectorXd s;
};

/**
 * @brief 对折线航点做圆弧倒角，返回稠密采样的可行路径。
 *
 * @param waypoints  [(x, y), ...] 顺序航点
 * @param turn_radius  期望最小转弯半径 R (m)
 * @param resolution   采样间距 (m)
 * @return 圆弧倒角结果 FilletResult
 */
FilletResult fillet_path(
    const std::vector<std::pair<double, double>>& waypoints,
    double turn_radius,
    double resolution);

/**
 * @brief 从离散点数值重算 (psi_continuous, kappa, s)。
 *
 * 供最小曲率精修改动点位后重新导出航向/曲率使用。
 */
GeometryResult recompute_geometry(
    const Eigen::VectorXd& xs,
    const Eigen::VectorXd& ys);

/**
 * @brief 累积弧长计算。
 */
Eigen::VectorXd arc_length(
    const Eigen::VectorXd& xs,
    const Eigen::VectorXd& ys);

}  // 命名空间 usv_planning
