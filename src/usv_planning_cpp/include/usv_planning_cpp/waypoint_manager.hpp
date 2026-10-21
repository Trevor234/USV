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
 * @file waypoint_manager.hpp
 * @brief 无人船任务航点管理（纯 C++，无 ROS 依赖）。
 *
 * 对应 Python 版本: usv_planning/waypoint_manager.py
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

  /// 检查是否到达当前航点，若已到达则推进到下一个。返回是否刚刚到达了一个航点。
  ///
  /// 到达判定为"圆内"或"已越过"二者之一。倒角(圆弧过渡)会让参考路径在
  /// 拐角处外切, 路径到航点的最近距离随转弯角急剧增大(90 度约 5m,
  /// 150 度约 34m), 远超 radius。若只用到航点的欧氏距离作判定, 密集或
  /// 大角度航点的到达事件永远不会触发, 任务永远无法完成。
  /// 因此同时接受"沿上一航段方向已越过该航点"。
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
  int  current_idx_      = 0;
  bool mission_complete_ = false;
};

}  // namespace usv_planning
