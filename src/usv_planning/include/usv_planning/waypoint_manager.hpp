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
 * @file waypoint_manager.hpp
 * @brief 无人船任务航点管理（无 ROS 依赖）。
 */

#pragma once

#include <cmath>
#include <string>
#include <vector>

namespace usv_planning {

/// 包含位置和到达半径的单个航点。
struct Waypoint {
  double x         = 0.0;
  double y         = 0.0;
  double radius    = 2.0;   // 到达判定半径 (m)
  double heading   = 0.0;   // 航点处期望航向角 (rad)
  double stay_time = 0.0;   // 到达后停留时间 (s)
};

/// 管理由有序航点组成的任务。
class WaypointManager {
 public:
  WaypointManager() = default;

  /// 添加单个航点。
  void add_waypoint(const Waypoint& wp);

  /// 清空所有航点并重置进度。
  void clear();

  /// 设置圆弧倒角参考转弯半径 (m)，用于计算中间航点外切允许的横向通过窗口。
  void set_turn_radius(double turn_radius) { turn_radius_ = turn_radius; }

  /// 检查是否到达当前航点，若已到达则推进到下一个。返回是否刚刚到达了一个航点。
  ///
  /// 到达判定按航点类型区分:
  ///   - 首航点 (idx==0): 圆内或沿首段方向已出发 (along > 0 且横向偏差合理);
  ///   - 中间拐点: 圆内或沿角平分线方向已越过拐角且横向偏差在倒角外切包络内;
  ///   - 终点航点 (idx==size-1): 仅限严格进入到达半径 dist < wp.radius 内完成。
  bool update_progress(double x, double y);

  /// 返回包含当前航点在内的后续航点（最多 lookahead 个）。
  std::vector<Waypoint> get_active_waypoints(int lookahead = 3) const;

  // ── 只读访问器 ──
  const std::vector<Waypoint>& waypoints() const { return waypoints_; }
  int  current_index() const { return current_idx_; }
  bool mission_complete() const { return mission_complete_; }
  const Waypoint& current_waypoint() const;

 private:
  std::vector<Waypoint> waypoints_;
  int    current_idx_      = 0;
  bool   mission_complete_ = false;
  double turn_radius_      = 4.0;
};

}  // 命名空间 usv_planning
