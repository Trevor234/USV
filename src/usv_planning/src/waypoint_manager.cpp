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
 * @file waypoint_manager.cpp
 * @brief WaypointManager 实现。
 */

#include "usv_planning/waypoint_manager.hpp"

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

}  // 命名空间 usv_planning
