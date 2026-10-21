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
 * @file waypoint_manager.cpp
 * @brief WaypointManager 实现。
 *
 * 对应 Python 版本: usv_planning/waypoint_manager.py
 */

#include "usv_planning_cpp/waypoint_manager.hpp"

#include <algorithm>
#include <cmath>

namespace usv_planning {

void WaypointManager::add_waypoint(const Waypoint& wp) {
  waypoints_.push_back(wp);
}

void WaypointManager::clear() {
  waypoints_.clear();
  current_idx_ = 0;
  mission_complete_ = false;
}

const Waypoint& WaypointManager::current_waypoint() const {
  if (mission_complete_) {
    return waypoints_.back();
  }
  return waypoints_[current_idx_];
}

bool WaypointManager::update_progress(double x, double y) {
  if (mission_complete_ || waypoints_.empty()) return false;

  const auto& wp = waypoints_[current_idx_];
  double dist = std::hypot(x - wp.x, y - wp.y);

  // 倒角会让参考路径在拐角处外切, 路径到航点的最近距离随转弯角急剧增大:
  //   turn_radius=12m 时 90 度约 5m、120 度约 12m、150 度约 34m。
  // 只按 radius(默认 2m) 判定, 大角度航点永远不会被认为到达, 任务卡死。
  //
  // 补充判据: 沿进入该航点的航段方向, 船是否已越过航点。
  // 投影 > 0 表示已越过; 仅在与航点距离足够近(避免绕远路时误判)时启用,
  // 该距离阈值按航段长度的一半放宽, 保证倒角外切点一定落在判定范围内。
  bool passed = false;
  if (current_idx_ > 0) {
    const auto& prev = waypoints_[current_idx_ - 1];
    double seg_x = wp.x - prev.x;
    double seg_y = wp.y - prev.y;
    double seg_len = std::hypot(seg_x, seg_y);
    if (seg_len > 1e-6) {
      double ux = seg_x / seg_len;
      double uy = seg_y / seg_len;
      double along = (x - wp.x) * ux + (y - wp.y) * uy;   // >0 = 已越过
      double lateral = std::abs((x - wp.x) * (-uy) + (y - wp.y) * ux);
      // 侧向偏差不超过倒角外切量级的一半, 且投影已越过航点
      double gate = std::max(wp.radius, 0.5 * seg_len);
      passed = (along > 0.0) && (std::hypot(along, lateral) < gate);
    }
  }

  if (dist < wp.radius || passed) {
    current_idx_++;
    if (current_idx_ >= static_cast<int>(waypoints_.size())) {
      mission_complete_ = true;
    }
    return true;
  }
  return false;
}

std::vector<Waypoint> WaypointManager::get_active_waypoints(
    int lookahead) const {
  if (mission_complete_) {
    return {waypoints_.back()};
  }
  int end = std::min(current_idx_ + lookahead,
                     static_cast<int>(waypoints_.size()));
  return {waypoints_.begin() + current_idx_,
          waypoints_.begin() + end};
}

}  // namespace usv_planning
