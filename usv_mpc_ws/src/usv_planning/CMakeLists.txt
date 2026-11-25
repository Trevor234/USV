cmake_minimum_required(VERSION 3.8)
project(usv_planning)

if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 17)
endif()

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# ── 查找依赖 ──────────────────────────────────────────────
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(std_msgs REQUIRED)
find_package(nav_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(mavros_msgs REQUIRED)
find_package(geographic_msgs REQUIRED)
find_package(Eigen3 REQUIRED)
find_package(yaml_cpp_vendor REQUIRED)
find_package(yaml-cpp REQUIRED)

# ── 纯逻辑库（不含 ROS 依赖，替代 numpy 数学运算） ──────
add_library(planning_lib
  src/waypoint_manager.cpp
  src/trajectory_optimizer.cpp
  src/speed_profile.cpp
)
target_include_directories(planning_lib PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)
target_link_libraries(planning_lib
  Eigen3::Eigen
  yaml-cpp
)

# ── 可执行文件 1: mission_bridge_node ─────────────────────
add_executable(mission_bridge_node
  src/mission_bridge_node.cpp
  src/mission_bridge_main.cpp
)
target_include_directories(mission_bridge_node PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)
ament_target_dependencies(mission_bridge_node
  rclcpp
  std_msgs
  nav_msgs
  geometry_msgs
  mavros_msgs
  geographic_msgs
)

# ── 可执行文件 2: path_planner_node ───────────────────────
add_executable(path_planner_node
  src/path_planner_node.cpp
  src/path_planner_main.cpp
)
target_include_directories(path_planner_node PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)
target_link_libraries(path_planner_node
  planning_lib
)
ament_target_dependencies(path_planner_node
  rclcpp
  std_msgs
  nav_msgs
  geometry_msgs
)

# ── 安装规则 ──────────────────────────────────────────────
install(TARGETS mission_bridge_node path_planner_node
  DESTINATION lib/${PROJECT_NAME}
)
install(DIRECTORY include/
  DESTINATION include
)

# ── 测试 ──────────────────────────────────────────────────
if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()

  find_package(ament_cmake_gtest REQUIRED)
  ament_add_gtest(test_planning test/test_planning.cpp)
  target_include_directories(test_planning PRIVATE
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  )
  target_link_libraries(test_planning planning_lib)
endif()

ament_package()
