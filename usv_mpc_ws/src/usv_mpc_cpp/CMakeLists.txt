cmake_minimum_required(VERSION 3.8)
project(usv_mpc_cpp)

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

# ── acados: 从源码树 ~/acados (运行时库) + 包内 vendored codegen ──
# ACADOS_SOURCE_DIR 由 env-hook 设为 ~/acados (含 include/ + lib/,提供
# libacados/libblasfeo/libhpipm 运行时库)。
# codegen 的 C 源码已 vendor 进 acados_generated/ (见 scripts/regenerate_acados_codegen.py),
# 由本包自行编译成 codegen_lib,不再依赖 ~/.cache/usv_mpc_acados/ 或 Python codegen。
set(ACADOS_SOURCE_DIR "$ENV{ACADOS_SOURCE_DIR}")
if(NOT ACADOS_SOURCE_DIR)
  set(ACADOS_SOURCE_DIR "$ENV{HOME}/acados")
endif()
set(ACADOS_INC_DIR "${ACADOS_SOURCE_DIR}/include")
set(ACADOS_LIB_DIR "${ACADOS_SOURCE_DIR}/lib")
# acados 依赖 blasfeo/hpipm 头文件 (含 blasfeo_target.h)
set(BLASFEO_INC_DIR "${ACADOS_SOURCE_DIR}/include/blasfeo/include")
set(HPIPM_INC_DIR "${ACADOS_SOURCE_DIR}/include/hpipm/include")

# vendored codegen 目录 (含 acados_solver_usv_dyn_nmpc.h + 全部生成 .c)
set(ACADOS_GEN_DIR "${CMAKE_CURRENT_SOURCE_DIR}/acados_generated")
if(NOT EXISTS "${ACADOS_GEN_DIR}/acados_solver_usv_dyn_nmpc.c")
  message(FATAL_ERROR
    "缺少 vendored acados codegen 源码 (${ACADOS_GEN_DIR})。"
    "请用 scripts/regenerate_acados_codegen.py 重新生成。")
endif()

# ── codegen 库: 编译 vendored 的生成 C 源码 (C99, 等价原 Makefile) ──
file(GLOB_RECURSE ACADOS_GEN_SRC "${ACADOS_GEN_DIR}/*.c")
add_library(codegen_lib STATIC ${ACADOS_GEN_SRC})
set_target_properties(codegen_lib PROPERTIES
  C_STANDARD 99
  POSITION_INDEPENDENT_CODE ON)
target_include_directories(codegen_lib PUBLIC
  $<BUILD_INTERFACE:${ACADOS_GEN_DIR}>
  $<INSTALL_INTERFACE:include/usv_mpc_cpp/acados_generated>
  ${ACADOS_INC_DIR}
  ${ACADOS_INC_DIR}/acados
  ${BLASFEO_INC_DIR}
  ${HPIPM_INC_DIR})
# 生成代码在 Pi5 GCC 下的良性告警 (未用参数等),不作为错误
target_compile_options(codegen_lib PRIVATE -w)
if(EXISTS "${ACADOS_LIB_DIR}/libacados.so")
  target_link_directories(codegen_lib PUBLIC ${ACADOS_LIB_DIR})
  target_link_libraries(codegen_lib PUBLIC acados hpipm blasfeo m)
endif()

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

find_package(Python3 REQUIRED COMPONENTS Interpreter)

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
  ${ACADOS_INC_DIR}
  ${BLASFEO_INC_DIR}
  ${HPIPM_INC_DIR}
  $<BUILD_INTERFACE:${ACADOS_GEN_DIR}>
  $<INSTALL_INTERFACE:include/usv_mpc_cpp/acados_generated>
)
target_link_libraries(mpc_solver_lib PUBLIC mpc_core_lib)
target_link_libraries(mpc_solver_lib PUBLIC nlohmann_json::nlohmann_json)
# acados 运行时库 (libacados/libblasfeo/libhpipm) + 包内 vendored codegen
if(EXISTS "${ACADOS_LIB_DIR}/libacados.so")
  target_link_directories(mpc_solver_lib PUBLIC ${ACADOS_LIB_DIR})
  target_link_libraries(mpc_solver_lib PUBLIC acados blasfeo hpipm)
endif()
target_link_libraries(mpc_solver_lib PUBLIC codegen_lib)
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

# ── RPATH: 让运行时找到 acados/casadi/blasfeo/hpipm .so ──
# codegen 已静态链接进 mpc_node,无需 codegen .so 路径。
set_target_properties(mpc_node PROPERTIES
  BUILD_RPATH "${ACADOS_LIB_DIR};${CASADI_LIB_DIR}"
  INSTALL_RPATH "$ORIGIN;$ENV{HOME}/acados/lib;${CASADI_LIB_DIR}"
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
  # vendored acados 生成码 (acados_generated/) + codegen 归档脚本 (scripts/) 不是手写
  # ROS 源码,不应受版权/风格检查。ament_lint_auto 无法按文件排除,故把会扫到它们的
  # linter 从 auto 剔除;C++ linter 改为只对手写目录 (src/include/test) 显式调用,
  # flake8/pep257 直接剔除 (包内唯一 .py 是 codegen 维护脚本)。
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
    BUILD_RPATH "${ACADOS_LIB_DIR};${CASADI_LIB_DIR}"
  )
  set_tests_properties(test_deadline_control PROPERTIES
    ENVIRONMENT "LD_LIBRARY_PATH=${ACADOS_LIB_DIR}:${CASADI_LIB_DIR}:$ENV{LD_LIBRARY_PATH};ROS_DOMAIN_ID=88;ROS_LOCALHOST_ONLY=1"
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
    BUILD_RPATH "${ACADOS_LIB_DIR};${CASADI_LIB_DIR}")
  set_tests_properties(test_research_contract PROPERTIES
    ENVIRONMENT "LD_LIBRARY_PATH=${ACADOS_LIB_DIR}:${CASADI_LIB_DIR}:$ENV{LD_LIBRARY_PATH};ROS_DOMAIN_ID=89;ROS_LOCALHOST_ONLY=1"
    TIMEOUT 120)

  if(EXISTS "${ACADOS_LIB_DIR}/libacados.so")
    ament_add_gtest(test_acados_solve test/test_acados_solve.cpp)
    target_include_directories(test_acados_solve PRIVATE
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    )
    target_link_libraries(test_acados_solve mpc_solver_lib)
    set_target_properties(test_acados_solve PROPERTIES
      BUILD_RPATH "${ACADOS_LIB_DIR};${CASADI_LIB_DIR}"
    )
    # RUNPATH 对间接依赖 (libacados.so -> libhpipm/libblasfeo) 不生效,
    # ctest 环境下需显式 LD_LIBRARY_PATH
    set_tests_properties(test_acados_solve PROPERTIES
      ENVIRONMENT "LD_LIBRARY_PATH=${ACADOS_LIB_DIR}:${CASADI_LIB_DIR}"
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
        BUILD_RPATH "${ACADOS_LIB_DIR};${CASADI_LIB_DIR}"
      )
      set_tests_properties(test_backend_consistency PROPERTIES
        ENVIRONMENT "LD_LIBRARY_PATH=${ACADOS_LIB_DIR}:${CASADI_LIB_DIR}"
      )
    endif()
  endif()
endif()

# P1_EXPORT_CORE_V1: backend has one owner in the independent solver process.
install(TARGETS mpc_core_lib mpc_solver_lib codegen_lib
  EXPORT p1_core_targets ARCHIVE DESTINATION lib LIBRARY DESTINATION lib RUNTIME DESTINATION bin)
install(DIRECTORY acados_generated/ DESTINATION include/usv_mpc_cpp/acados_generated FILES_MATCHING PATTERN "*.h")
ament_export_targets(p1_core_targets HAS_LIBRARY_TARGET NAMESPACE usv_mpc_cpp::)
ament_export_dependencies(Eigen3 nlohmann_json)

ament_package()
