cmake_minimum_required(VERSION 3.8)
project(usv_safety_cpp)

# 使用 C++17 标准（现代特性：结构化绑定、std::optional 等）
if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 17)
endif()
if(NOT CMAKE_CXX_STANDARD_REQUIRED)
  set(CMAKE_CXX_STANDARD_REQUIRED ON)
endif()

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# ── 查找依赖 ──────────────────────────────────────────────
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(std_msgs REQUIRED)
find_package(nav_msgs REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(mavros_msgs REQUIRED)
find_package(nlohmann_json REQUIRED)

# ── 纯逻辑库（不含 ROS 依赖，方便独立测试） ─────────────
add_library(safety_monitor_lib
  src/safety_monitor.cpp
)
target_include_directories(safety_monitor_lib PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)

# ── 可执行文件：mode_manager_node ─────────────────────────
add_executable(mode_manager_node
  src/mode_manager_node.cpp
  src/main.cpp
)
target_include_directories(mode_manager_node PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)
target_link_libraries(mode_manager_node
  safety_monitor_lib
)
ament_target_dependencies(mode_manager_node
  rclcpp
  std_msgs
  nav_msgs
  sensor_msgs
  geometry_msgs
  mavros_msgs
  nlohmann_json
)

# ── 安装规则 ──────────────────────────────────────────────
install(TARGETS mode_manager_node
  DESTINATION lib/${PROJECT_NAME}
)
install(DIRECTORY include/
  DESTINATION include
)

# ── 测试 ──────────────────────────────────────────────────
if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()

  # gtest: SafetyMonitor 纯逻辑单测
  find_package(ament_cmake_gtest REQUIRED)
  ament_add_gtest(test_safety_monitor test/test_safety_monitor.cpp)
  target_include_directories(test_safety_monitor PRIVATE
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  )
  target_link_libraries(test_safety_monitor safety_monitor_lib)
endif()

ament_package()
