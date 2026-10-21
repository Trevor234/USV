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
  if (dist < wp.radius) {
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
