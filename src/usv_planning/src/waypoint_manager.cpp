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
  if (mission_complete_ || waypoints_.empty() ||
      !std::isfinite(x) || !std::isfinite(y)) {
    return false;
  }

  const int n = static_cast<int>(waypoints_.size());
  bool advanced = false;

  while (!mission_complete_ && current_idx_ < n) {
    const auto& wp = waypoints_[current_idx_];
    const double dist = std::hypot(x - wp.x, y - wp.y);
    bool reached = (dist < wp.radius);

    if (!reached && current_idx_ == 0 && n >= 2) {
      // 首航点: 若船体位于首段方向前方且横向偏离在合理范围内，视为已出发越过。
      const auto& next = waypoints_[1];
      const double seg_x = next.x - wp.x;
      const double seg_y = next.y - wp.y;
      const double seg_len = std::hypot(seg_x, seg_y);
      if (seg_len > 1e-6) {
        const double ux = seg_x / seg_len;
        const double uy = seg_y / seg_len;
        const double along = (x - wp.x) * ux + (y - wp.y) * uy;
        const double lateral = std::abs((x - wp.x) * (-uy) + (y - wp.y) * ux);
        const double gate_lateral = std::max(wp.radius * 2.0, 10.0);
        reached = (along > 0.0) && (lateral < gate_lateral);
      }
    } else if (!reached && current_idx_ > 0 && current_idx_ < n - 1) {
      // 中间拐点: 沿入/出航段角平分线方向构建法平面投影 (适配 0~179° 大转角倒角),
      // 并将纵向通过窗与圆弧外切横向包络解耦限制。
      const auto& prev = waypoints_[current_idx_ - 1];
      const auto& next = waypoints_[current_idx_ + 1];
      const double in_x = wp.x - prev.x;
      const double in_y = wp.y - prev.y;
      const double out_x = next.x - wp.x;
      const double out_y = next.y - wp.y;
      const double len_in = std::hypot(in_x, in_y);
      const double len_out = std::hypot(out_x, out_y);
      if (len_in > 1e-6 && len_out > 1e-6) {
        const double uin_x = in_x / len_in;
        const double uin_y = in_y / len_in;
        const double uout_x = out_x / len_out;
        const double uout_y = out_y / len_out;

        double bx = uin_x + uout_x;
        double by = uin_y + uout_y;
        const double b_len = std::hypot(bx, by);
        if (b_len > 1e-6) {
          bx /= b_len;
          by /= b_len;
        } else {
          bx = uin_x;
          by = uin_y;
        }

        const double dot = std::clamp(uin_x * uout_x + uin_y * uout_y, -1.0, 1.0);
        const double delta = std::acos(dot);
        const double tan_half = std::tan(0.5 * delta);
        const double R = std::max(1e-3, turn_radius_);
        const double T = std::min(R * tan_half, std::min(len_in, 0.5 * len_out));
        // 圆弧中点到角点理论外切偏移 = T * tan(delta / 4), 对全角度有界 (<= T)
        const double fillet_offset = T * std::tan(0.25 * delta);
        const double gate_lateral = std::max(wp.radius * 1.5, fillet_offset + wp.radius);
        const double gate_along = std::max(wp.radius, 0.35 * len_in);

        const double along = (x - wp.x) * bx + (y - wp.y) * by;
        const double lateral = std::abs((x - wp.x) * (-by) + (y - wp.y) * bx);
        reached = (along > 0.0) && (along < gate_along) && (lateral < gate_lateral);
      }
    }
    // 终点航点 (current_idx_ == n - 1): 不使用倒角放大圈, 仅允许 dist < wp.radius。

    if (!reached) {
      break;
    }
    advanced = true;
    current_idx_++;
    if (current_idx_ >= n) {
      mission_complete_ = true;
    }
  }
  return advanced;
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
