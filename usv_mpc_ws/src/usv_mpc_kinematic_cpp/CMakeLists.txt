cmake_minimum_required(VERSION 3.8)
project(usv_mpc_kinematic_cpp)

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
find_package(Python3 REQUIRED COMPONENTS Interpreter)

# ── CasADi C++ (pip wheel) ───────────────────────────────
# 路径: ~/.local/lib/python3.12/site-packages/casadi/{include,lib}
# (与方案 B 同探测逻辑; acados 段在此方案 A 中不需要)
set(CASADI_INC_DIR "")
set(CASADI_LIB_DIR "")
execute_process(
  COMMAND "${Python3_EXECUTABLE}" -c "import casadi,os;print(os.path.dirname(casadi.__file__))"
  OUTPUT_VARIABLE CASADI_PKG_DIR OUTPUT_STRIP_TRAILING_WHITESPACE
  RESULT_VARIABLE CASADI_PKG_RC)

# ABI 探针: CasADi 官方 pip wheel 历史上以旧 C++ ABI (_GLIBCXX_USE_CXX11_ABI=0) 构建,
# 与系统 GCC 默认新 ABI 的用户代码修饰名不一致 (链接期 undefined reference)。
# 故实际试链一个使用 Opti 的最小程序, 成功才启用 CasADi 后端。
if(CASADI_PKG_RC EQUAL 0 AND EXISTS "${CASADI_PKG_DIR}/include/casadi/casadi.hpp")
  set(CASADI_INC_DIR "${CASADI_PKG_DIR}/include")
  set(CASADI_LIB_DIR "${CASADI_PKG_DIR}")
  set(CASADI_PROBE_DIR "${CMAKE_CURRENT_BINARY_DIR}/casadi_abi_probe")
  file(MAKE_DIRECTORY "${CASADI_PROBE_DIR}")
  file(WRITE "${CASADI_PROBE_DIR}/probe.cpp"
    "#include <casadi/casadi.hpp>\n"
    "int main() { casadi::Opti o; o.subject_to(o.x() >= 0); return 0; }\n")
  execute_process(
    COMMAND "${CMAKE_CXX_COMPILER}" "${CASADI_PROBE_DIR}/probe.cpp"
            "-I${CASADI_INC_DIR}" "-L${CASADI_LIB_DIR}"
            "-Wl,-rpath,${CASADI_LIB_DIR}" "-lcasadi"
            "-o" "${CASADI_PROBE_DIR}/probe"
    RESULT_VARIABLE CASADI_PROBE_RC OUTPUT_QUIET ERROR_QUIET
    TIMEOUT 120)
  # pip wheel 历史上以旧 C++ ABI 构建: 新 ABI 链接失败时, 再用
  # -D_GLIBCXX_USE_CXX11_ABI=0 重试探针 (2026-09-06, 实测 wheel 可用)
  set(CASADI_ABI_FLAG "")
  if(NOT CASADI_PROBE_RC EQUAL 0)
    execute_process(
      COMMAND "${CMAKE_CXX_COMPILER}" "-D_GLIBCXX_USE_CXX11_ABI=0"
              "${CASADI_PROBE_DIR}/probe.cpp"
              "-I${CASADI_INC_DIR}" "-L${CASADI_LIB_DIR}"
              "-Wl,-rpath,${CASADI_LIB_DIR}" "-lcasadi"
              "-o" "${CASADI_PROBE_DIR}/probe_oldabi"
      RESULT_VARIABLE CASADI_PROBE_RC OUTPUT_QUIET ERROR_QUIET
      TIMEOUT 120)
    if(CASADI_PROBE_RC EQUAL 0)
      set(CASADI_ABI_FLAG "-D_GLIBCXX_USE_CXX11_ABI=0")
      message(STATUS "CasADi C++ found (旧 ABI wheel, 编译匹配旧 ABI): ${CASADI_PKG_DIR}")
    endif()
  endif()
  if(CASADI_ABI_FLAG)
    # 旧 ABI 标志只作用于包含 casadi 头的翻译单元
    set_source_files_properties(
      "${CMAKE_CURRENT_SOURCE_DIR}/src/casadi_kinematic_backend.cpp"
      "${CMAKE_CURRENT_SOURCE_DIR}/src/kinematic_mpc_solver.cpp"
      PROPERTIES COMPILE_OPTIONS "${CASADI_ABI_FLAG}")
  endif()

  if(CASADI_PROBE_RC EQUAL 0)
    set(CASADI_FOUND TRUE)
    message(STATUS "CasADi C++ found (ABI probe OK): ${CASADI_PKG_DIR}")
  else()
    set(CASADI_FOUND FALSE)
    message(WARNING
      "CasADi C++ ABI 探针失败 (pip wheel 为旧 C++ ABI 构建), "
      "运动学 C++ MPC 后端不可用; 方案 A 请用 Python usv_mpc")
  endif()
else()
  set(CASADI_FOUND FALSE)
  message(WARNING "CasADi C++ 未找到, 运动学 MPC 后端不可用")
endif()

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

# ── 求解器库: casadi 后端 + 工厂 ─────────────────────────
# (对齐 B 的 mpc_solver_lib; A 无 acados_backend, 无 blasfeo/hpipm)
# casadi_kinematic_backend 仅在 ABI 探针通过时编译 (见上方 CasADi 探测)。
set(MPC_SOLVER_LIB_SRC src/kinematic_mpc_solver.cpp)
if(CASADI_FOUND)
  list(APPEND MPC_SOLVER_LIB_SRC src/casadi_kinematic_backend.cpp)
endif()
add_library(mpc_solver_lib ${MPC_SOLVER_LIB_SRC})
target_include_directories(mpc_solver_lib PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)
target_link_libraries(mpc_solver_lib PUBLIC mpc_core_lib)
target_link_libraries(mpc_solver_lib PUBLIC nlohmann_json::nlohmann_json)
# CasADi (与 B 同)
if(CASADI_FOUND)
  target_include_directories(mpc_solver_lib PUBLIC ${CASADI_INC_DIR})
  target_link_directories(mpc_solver_lib PUBLIC ${CASADI_LIB_DIR})
  target_link_libraries(mpc_solver_lib PUBLIC casadi)
  # 供 kinematic_mpc_solver.cpp 工厂用 #ifdef 选择后端
  target_compile_definitions(mpc_solver_lib PUBLIC USV_MPC_HAS_CASADI)
endif()

# ── 可执行文件: mpc_node ─────────────────────────────────
# (可执行名对齐 B 与 Python 入口; scaffold 原名 mpc_controller_node 已弃用)
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

# ── RPATH: 让运行时找到 casadi .so ───────────────────────
# (B 还含 acados 路径; A 仅 casadi)
set_target_properties(mpc_node PROPERTIES
  BUILD_RPATH "${CASADI_LIB_DIR}"
  INSTALL_RPATH "$ORIGIN;${CASADI_LIB_DIR}"
)

# ── 安装 ──────────────────────────────────────────────────
install(TARGETS mpc_node
  DESTINATION lib/${PROJECT_NAME}
)
install(DIRECTORY include/
  DESTINATION include
)

# ── 测试 ──────────────────────────────────────────────────
if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()

  # gtest: 纯逻辑层 (model+utils), 不依赖 casadi/ros
  find_package(ament_cmake_gtest REQUIRED)
  ament_add_gtest(test_mpc_core test/test_mpc_core.cpp)
  target_include_directories(test_mpc_core PRIVATE
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  )
  # 链接 mpc_solver_lib: 使 ABI 跨界测试在新 ABI 测试 TU 中调用 old-ABI casadi 后端
  target_link_libraries(test_mpc_core mpc_solver_lib)
endif()

ament_package()
