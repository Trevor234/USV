cmake_minimum_required(VERSION 3.8)
project(usv_mpc)

# ── 构建类型默认值 ────────────────────────────────────────
# 单配置生成器 (Makefiles/Ninja) 未显式指定 CMAKE_BUILD_TYPE 时默认 Release,
# 避免空缓存导致的“无优化构建被当成发布版”。多配置生成器不动。
if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
  set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
endif()

# 离线基线诊断程序 (benchmark_kinematic_solver) 开关: 默认关闭, 且不安装。
option(USV_BUILD_BASELINE_BENCHMARK
  "构建 NoOpt/Release 离线基线诊断程序 (不安装)" OFF)

if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 17)
endif()
if(NOT CMAKE_CXX_STANDARD_REQUIRED)
  set(CMAKE_CXX_STANDARD_REQUIRED ON)
endif()

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# ── 查找 ROS 依赖 ────────────────────────────────────────
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(nav_msgs REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(mavros_msgs REQUIRED)
find_package(std_msgs REQUIRED)
find_package(nlohmann_json REQUIRED)
find_package(Eigen3 REQUIRED)

# ── acados 运行时库 (经由共用后端库 usv_acados::backend) ────────────
# 方案 A 的运动学 OCP 生成码与求解循环都在 usv_acados 包里; 本包只保留
# p_global 组装、参数校验、四残差门禁与 ROS 节点。不再链接/import CasADi。
find_package(usv_acados REQUIRED)

set(ACADOS_SOURCE_DIR "$ENV{ACADOS_SOURCE_DIR}")
if(NOT ACADOS_SOURCE_DIR)
  set(ACADOS_SOURCE_DIR "$ENV{HOME}/acados")
endif()
set(ACADOS_LIB_DIR "${ACADOS_SOURCE_DIR}/lib")
if(NOT EXISTS "${ACADOS_LIB_DIR}/libacados.so")
  message(FATAL_ERROR
    "未找到 acados 运行时库 (${ACADOS_LIB_DIR}/libacados.so)。"
    "usv_mpc 仅使用 acados 后端，请先编译安装 acados 或设置 ACADOS_SOURCE_DIR。")
endif()

# 共用后端库的实际安装目录 (来自 find_package 的配置目录, 候选不搬移)。
get_filename_component(_usv_acados_prefix "${usv_acados_DIR}/../../.." ABSOLUTE)
set(USV_ACADOS_BACKEND_DIR "${_usv_acados_prefix}/lib")

# ── 纯逻辑库: model + utils ──────────────────────────────
# (对齐 B 的 mpc_core_lib; A 用 usv_model_kinematic 替代 usv_model_dynamic)
add_library(mpc_core_lib
  src/usv_model_kinematic.cpp
  src/utils.cpp
)
target_include_directories(mpc_core_lib PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)
target_link_libraries(mpc_core_lib PUBLIC Eigen3::Eigen)
# mpc_core_lib 不链 ROS (utils 是纯逻辑, 保持可单测)

# ── 求解器库: acados 适配器 + 残差门禁 + 工厂 ───────────────────
add_library(mpc_solver_lib
  src/kinematic_mpc_solver.cpp
  src/acados_kinematic_backend.cpp
  src/kinematic_solution_audit.cpp
)
target_include_directories(mpc_solver_lib PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)
target_link_libraries(mpc_solver_lib PUBLIC mpc_core_lib)
target_link_libraries(mpc_solver_lib PUBLIC nlohmann_json::nlohmann_json)
# 共用的 acados 求解引擎 (含两套 vendored 生成码与 acados/hpipm/blasfeo 链接)
target_link_libraries(mpc_solver_lib PUBLIC usv_acados::backend)

# ── 可执行文件: mpc_node ─────────────────────────────────
# (可执行名与方案 B 保持一致)
add_executable(mpc_node
  src/mpc_node.cpp
  src/mpc_node_main.cpp
)
target_include_directories(mpc_node PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)
target_link_libraries(mpc_node mpc_solver_lib)
ament_target_dependencies(mpc_node
  rclcpp
  geometry_msgs
  nav_msgs
  sensor_msgs
  mavros_msgs
  std_msgs
  nlohmann_json
)

# ── RPATH: 让运行时找到共用后端库与 acados .so ─────────────
# 候选目录不搬移, 安装后直接指向本候选的共用库所在目录。
set_target_properties(mpc_node PROPERTIES
  BUILD_RPATH "${USV_ACADOS_BACKEND_DIR};${ACADOS_LIB_DIR}"
  INSTALL_RPATH "${USV_ACADOS_BACKEND_DIR};${ACADOS_LIB_DIR}"
)

# ── 安装 ──────────────────────────────────────────────────
install(TARGETS mpc_node
  DESTINATION lib/${PROJECT_NAME}
)
install(DIRECTORY include/
  DESTINATION include
)

# ── 离线基线诊断程序 (不安装) ─────────────────────────────
# 固定输入下直接调用求解器, 用于同一冻结源码的 NoOpt/Release 数值与耗时对照。
# 参数解析直接复用 rclcpp 的 YAML 参数设施 (不创建 ROS 通信节点)。
if(USV_BUILD_BASELINE_BENCHMARK)
  add_executable(benchmark_kinematic_solver test/benchmark_solver.cpp)
  target_include_directories(benchmark_kinematic_solver PRIVATE
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  )
  target_link_libraries(benchmark_kinematic_solver mpc_solver_lib)
  ament_target_dependencies(benchmark_kinematic_solver
    rclcpp
    nlohmann_json
  )
  set_target_properties(benchmark_kinematic_solver PROPERTIES
    BUILD_RPATH "${USV_ACADOS_BACKEND_DIR};${ACADOS_LIB_DIR}"
  )
endif()

# ── 测试 ──────────────────────────────────────────────────
if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  list(APPEND AMENT_LINT_AUTO_EXCLUDE
    ament_cmake_copyright
    ament_cmake_cpplint
    ament_cmake_uncrustify
  )
  ament_lint_auto_find_test_dependencies()

  set(_lint_dirs src include test)
  find_package(ament_cmake_copyright REQUIRED)
  ament_copyright(${_lint_dirs})
  find_package(ament_cmake_cpplint REQUIRED)
  ament_cpplint(${_lint_dirs})
  find_package(ament_cmake_uncrustify REQUIRED)
  ament_uncrustify(${_lint_dirs})

  # gtest: 纯逻辑层 (model+utils), 不依赖 acados/ros
  find_package(ament_cmake_gtest REQUIRED)
  ament_add_gtest(test_mpc_core test/test_mpc_core.cpp)
  target_include_directories(test_mpc_core PRIVATE
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  )
  target_link_libraries(test_mpc_core mpc_core_lib)

  # gtest: 运动学 acados 后端真实求解行为 + 候选门禁
  ament_add_gtest(test_acados_kinematic test/test_acados_kinematic.cpp)
  target_include_directories(test_acados_kinematic PRIVATE
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  )
  target_link_libraries(test_acados_kinematic mpc_solver_lib)
  set_target_properties(test_acados_kinematic PROPERTIES
    BUILD_RPATH "${USV_ACADOS_BACKEND_DIR};${ACADOS_LIB_DIR}"
  )
  set_tests_properties(test_acados_kinematic PROPERTIES ENVIRONMENT_MODIFICATION
    "LD_LIBRARY_PATH=path_list_prepend:${USV_ACADOS_BACKEND_DIR};LD_LIBRARY_PATH=path_list_prepend:${ACADOS_LIB_DIR}"
  )

  # gtest: 安全修复回归 (C1 recheck / C2 关机锁 / M2 墙钟 deadline / M1 四元数门禁)
  # 注入 FakeKinematicMpc, 不依赖 acados。
  # mpc_node.cpp 需直接编进测试 —— 节点实现不在任何库里。
  ament_add_gtest(test_deadline_control
    test/test_deadline_control.cpp
    src/mpc_node.cpp
  )
  target_include_directories(test_deadline_control PRIVATE
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  )
  target_link_libraries(test_deadline_control mpc_solver_lib)
  ament_target_dependencies(test_deadline_control
    rclcpp
    geometry_msgs
    nav_msgs
    sensor_msgs
    mavros_msgs
    std_msgs
    nlohmann_json
  )
  set_target_properties(test_deadline_control PROPERTIES
    BUILD_RPATH "${USV_ACADOS_BACKEND_DIR};${ACADOS_LIB_DIR}"
  )
  set_tests_properties(test_deadline_control PROPERTIES ENVIRONMENT_MODIFICATION
    "LD_LIBRARY_PATH=path_list_prepend:${USV_ACADOS_BACKEND_DIR};LD_LIBRARY_PATH=path_list_prepend:${ACADOS_LIB_DIR}"
  )
endif()

ament_package()
