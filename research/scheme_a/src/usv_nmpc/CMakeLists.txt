cmake_minimum_required(VERSION 3.8)
project(usv_nmpc)

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
find_package(rclcpp_components REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(nav_msgs REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(mavros_msgs REQUIRED)
find_package(std_msgs REQUIRED)
find_package(rosgraph_msgs REQUIRED)
find_package(usv_research_interfaces REQUIRED)
find_package(nlohmann_json REQUIRED)
find_package(Eigen3 REQUIRED)

# ── acados 运行时库 (经由共用后端库 usv_acados::backend) ──────────────
# 方案 B 的动力学 OCP 生成码与求解循环都在 usv_acados 包里
# (src/usv_acados/acados_generated/dynamic/, usv_dyn_nmpc_*); 本包只保留
# p_global 组装、权重校验、连续失败计数与分级安全回退。
find_package(usv_acados REQUIRED)

set(ACADOS_SOURCE_DIR "$ENV{ACADOS_SOURCE_DIR}")
if(NOT ACADOS_SOURCE_DIR)
  set(ACADOS_SOURCE_DIR "$ENV{HOME}/acados")
endif()
set(ACADOS_LIB_DIR "${ACADOS_SOURCE_DIR}/lib")
if(NOT EXISTS "${ACADOS_LIB_DIR}/libacados.so")
  message(FATAL_ERROR
    "未找到 acados 运行时库 (${ACADOS_LIB_DIR}/libacados.so)。"
    "请先编译安装 acados 或设置 ACADOS_SOURCE_DIR。")
endif()

# 共用后端库的实际安装目录 (来自 find_package 的配置目录, 候选不搬移)。
get_filename_component(_usv_acados_prefix "${usv_acados_DIR}/../../.." ABSOLUTE)
set(USV_ACADOS_BACKEND_DIR "${_usv_acados_prefix}/lib")

# ── Python: CasADi 探测需要解释器 (必须在探测之前确定) ──────────────
find_package(Python3 REQUIRED COMPONENTS Interpreter)

# ── CasADi C++ (pip wheel) ───────────────────────────────
# 路径: ~/.local/lib/python3.12/site-packages/casadi/{include,lib}
set(CASADI_INC_DIR "")
set(CASADI_LIB_DIR "")
execute_process(
  COMMAND "${Python3_EXECUTABLE}" -c "import casadi,os;print(os.path.dirname(casadi.__file__))"
  OUTPUT_VARIABLE CASADI_PKG_DIR OUTPUT_STRIP_TRAILING_WHITESPACE
  RESULT_VARIABLE CASADI_PKG_RC)

# ABI 探针: CasADi 官方 pip wheel 历史上以旧 C++ ABI (_GLIBCXX_USE_CXX11_ABI=0) 构建,
# 与系统 GCC 默认新 ABI 的用户代码修饰名不一致 (链接期 undefined reference)。
# 故实际试链一个使用 Opti 的最小程序, 成功才启用 CasADi fallback 后端。
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
      "${CMAKE_CURRENT_SOURCE_DIR}/src/casadi_backend.cpp"
      "${CMAKE_CURRENT_SOURCE_DIR}/src/mpc_solver.cpp"
      PROPERTIES COMPILE_OPTIONS "${CASADI_ABI_FLAG}")
  endif()

  if(CASADI_PROBE_RC EQUAL 0)
    set(CASADI_FOUND TRUE)
    message(STATUS "CasADi C++ found (ABI probe OK): ${CASADI_PKG_DIR}")
  else()
    set(CASADI_FOUND FALSE)
    message(WARNING
      "CasADi C++ ABI 探针失败 (pip wheel 为旧 C++ ABI 构建), "
      "fallback 后端不可用, 仅 acados 后端")
  endif()
else()
  set(CASADI_FOUND FALSE)
  message(WARNING "CasADi C++ 未找到,fallback 后端不可用 (仅 acados)")
endif()

# ── 纯逻辑库: model + utils ──────────────────────────────
add_library(mpc_core_lib
  src/usv_model_dynamic.cpp
  src/utils.cpp
  src/p1_input_core.cpp
)
target_include_directories(mpc_core_lib PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)
target_link_libraries(mpc_core_lib PUBLIC Eigen3::Eigen)

# ── 求解器库: acados + casadi 后端 + 工厂 ────────────────
# casadi_backend 仅在 ABI 探针通过时编译 (见上方 CasADi 探测)。
set(MPC_SOLVER_LIB_SRC
  src/mpc_solver.cpp
  src/acados_backend.cpp
)
if(CASADI_FOUND)
  list(APPEND MPC_SOLVER_LIB_SRC src/casadi_backend.cpp)
endif()
add_library(mpc_solver_lib ${MPC_SOLVER_LIB_SRC})
target_include_directories(mpc_solver_lib PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)
target_link_libraries(mpc_solver_lib PUBLIC mpc_core_lib)
target_link_libraries(mpc_solver_lib PUBLIC nlohmann_json::nlohmann_json)
# 共用的 acados 求解引擎 (含两套 vendored 生成码与 acados/hpipm/blasfeo 链接)
target_link_libraries(mpc_solver_lib PUBLIC usv_acados::backend)
# CasADi
if(CASADI_FOUND)
  target_include_directories(mpc_solver_lib PUBLIC ${CASADI_INC_DIR})
  target_link_directories(mpc_solver_lib PUBLIC ${CASADI_LIB_DIR})
  target_link_libraries(mpc_solver_lib PUBLIC casadi)
  # 供 mpc_solver.cpp 工厂用 #ifdef 选择 fallback
  target_compile_definitions(mpc_solver_lib PUBLIC USV_MPC_HAS_CASADI)
endif()

# ── 可执行文件: mpc_node ─────────────────────────────────
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
  rosgraph_msgs
  usv_research_interfaces
)

# ── RPATH: 让运行时找到共用后端库与 acados/casadi/blasfeo/hpipm .so ──
# 生成码在共用库内部, mpc_node 只需找到 libusv_acados_backend.so 与 acados 运行时。
set_target_properties(mpc_node PROPERTIES
  BUILD_RPATH "${USV_ACADOS_BACKEND_DIR};${ACADOS_LIB_DIR};${CASADI_LIB_DIR}"
  INSTALL_RPATH "$ORIGIN;${USV_ACADOS_BACKEND_DIR};$ENV{HOME}/acados/lib;${CASADI_LIB_DIR}"
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
  # C++ linter 只对手写目录 (src/include/test) 显式调用; flake8/pep257 保留剔除
  # (本包无 .py 源文件), 与共用包 usv_acados 的 linter 配置保持一致。
  list(APPEND AMENT_LINT_AUTO_EXCLUDE
    ament_cmake_copyright
    ament_cmake_cpplint
    ament_cmake_uncrustify
    ament_cmake_flake8
    ament_cmake_pep257
  )
  ament_lint_auto_find_test_dependencies()

  set(_lint_dirs src include test)
  find_package(ament_cmake_copyright REQUIRED)
  ament_copyright(${_lint_dirs})
  find_package(ament_cmake_cpplint REQUIRED)
  ament_cpplint(${_lint_dirs})
  find_package(ament_cmake_uncrustify REQUIRED)
  ament_uncrustify(${_lint_dirs})

  # gtest: 纯逻辑层 (model+utils), 不依赖 acados/casadi
  find_package(ament_cmake_gtest REQUIRED)
  ament_add_gtest(test_mpc_core test/test_mpc_core.cpp)
  target_include_directories(test_mpc_core PRIVATE
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  )
  target_link_libraries(test_mpc_core mpc_core_lib)

  # Exercise the node's actual output mapping using an injected test solver.
  ament_add_gtest(test_deadline_control
    test/test_deadline_control.cpp src/mpc_node.cpp)
  target_include_directories(test_deadline_control PRIVATE
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  )
  target_link_libraries(test_deadline_control mpc_solver_lib)
  ament_target_dependencies(test_deadline_control
    rclcpp geometry_msgs nav_msgs sensor_msgs mavros_msgs std_msgs nlohmann_json rosgraph_msgs usv_research_interfaces)
  set_target_properties(test_deadline_control PROPERTIES
    BUILD_RPATH "${USV_ACADOS_BACKEND_DIR};${ACADOS_LIB_DIR};${CASADI_LIB_DIR}"
  )
  # LD 顺序敏感: casadi pip wheel 自带 libhpipm.so (与系统 acados 的 hpipm ABI
  # 不同) 与 SONAME 不同的 libblasfeo.so。path_list_prepend 逐条前置, 最后的
  # 条目排最前, 因此按 casadi -> acados -> backend 列出, 实际顺序为
  # backend:acados:casadi, 保证 acados 的 hpipm 先被找到。
  set_tests_properties(test_deadline_control PROPERTIES
    ENVIRONMENT "ROS_DOMAIN_ID=88;ROS_LOCALHOST_ONLY=1"
    ENVIRONMENT_MODIFICATION
      "LD_LIBRARY_PATH=path_list_prepend:${CASADI_LIB_DIR};LD_LIBRARY_PATH=path_list_prepend:${ACADOS_LIB_DIR};LD_LIBRARY_PATH=path_list_prepend:${USV_ACADOS_BACKEND_DIR}"
    TIMEOUT 60
  )

  # gtest: acados 后端冒烟 + K1/K2 运行时约束边界回归 (需 acados 运行时库)
  ament_add_gtest(test_research_contract
    test/test_research_contract.cpp src/mpc_node.cpp)
  target_include_directories(test_research_contract PRIVATE
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>)
  target_link_libraries(test_research_contract mpc_solver_lib)
  ament_target_dependencies(test_research_contract
    rclcpp geometry_msgs nav_msgs sensor_msgs mavros_msgs std_msgs nlohmann_json
    rosgraph_msgs usv_research_interfaces)
  set_target_properties(test_research_contract PROPERTIES
    BUILD_RPATH "${USV_ACADOS_BACKEND_DIR};${ACADOS_LIB_DIR};${CASADI_LIB_DIR}")
  set_tests_properties(test_research_contract PROPERTIES
    ENVIRONMENT "ROS_DOMAIN_ID=89;ROS_LOCALHOST_ONLY=1"
    ENVIRONMENT_MODIFICATION
      "LD_LIBRARY_PATH=path_list_prepend:${CASADI_LIB_DIR};LD_LIBRARY_PATH=path_list_prepend:${ACADOS_LIB_DIR};LD_LIBRARY_PATH=path_list_prepend:${USV_ACADOS_BACKEND_DIR}"
    TIMEOUT 120)

  if(EXISTS "${ACADOS_LIB_DIR}/libacados.so")
    ament_add_gtest(test_acados_solve test/test_acados_solve.cpp)
    target_include_directories(test_acados_solve PRIVATE
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    )
    target_link_libraries(test_acados_solve mpc_solver_lib)
    set_target_properties(test_acados_solve PROPERTIES
      BUILD_RPATH "${USV_ACADOS_BACKEND_DIR};${ACADOS_LIB_DIR};${CASADI_LIB_DIR}"
    )
    # RUNPATH 对间接依赖 (libusv_acados_backend.so -> libacados.so -> libhpipm/
    # libblasfeo) 不生效, ctest 环境下需显式前置 LD_LIBRARY_PATH。
    set_tests_properties(test_acados_solve PROPERTIES
      ENVIRONMENT_MODIFICATION
        "LD_LIBRARY_PATH=path_list_prepend:${CASADI_LIB_DIR};LD_LIBRARY_PATH=path_list_prepend:${ACADOS_LIB_DIR};LD_LIBRARY_PATH=path_list_prepend:${USV_ACADOS_BACKEND_DIR}"
    )

    # 两个后端求解同一 OCP 的回归。测试通过不含 CasADi 类型的抽象工厂
    # 构造 fallback，避免 pip wheel 的旧 C++ ABI 泄漏到 gtest 翻译单元。
    if(CASADI_FOUND)
      ament_add_gtest(test_backend_consistency test/test_backend_consistency.cpp)
      target_include_directories(test_backend_consistency PRIVATE
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
      )
      target_link_libraries(test_backend_consistency mpc_solver_lib)
      set_target_properties(test_backend_consistency PROPERTIES
        BUILD_RPATH "${USV_ACADOS_BACKEND_DIR};${ACADOS_LIB_DIR};${CASADI_LIB_DIR}"
      )
      set_tests_properties(test_backend_consistency PROPERTIES
        ENVIRONMENT_MODIFICATION
          "LD_LIBRARY_PATH=path_list_prepend:${CASADI_LIB_DIR};LD_LIBRARY_PATH=path_list_prepend:${ACADOS_LIB_DIR};LD_LIBRARY_PATH=path_list_prepend:${USV_ACADOS_BACKEND_DIR}"
      )
    endif()
  endif()
endif()

# P1_EXPORT_CORE_V1: backend has one owner in the independent solver process.
install(TARGETS mpc_core_lib mpc_solver_lib
  EXPORT p1_core_targets ARCHIVE DESTINATION lib LIBRARY DESTINATION lib RUNTIME DESTINATION bin)
ament_export_targets(p1_core_targets HAS_LIBRARY_TARGET NAMESPACE usv_nmpc::)
ament_export_dependencies(Eigen3 nlohmann_json usv_acados)

ament_package()
