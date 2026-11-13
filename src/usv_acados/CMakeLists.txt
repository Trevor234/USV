cmake_minimum_required(VERSION 3.8)
project(usv_acados)

# ── 方案 A/B 共用的 acados 后端运行时库 ───────────────────────────────
# 本包只包含: 两套 vendored 生成码 (kinematic/dynamic) + 共用求解循环。
# 不含 ROS 依赖, 也不含任何方案语义 (残差门禁、失败回退、p_global 组装
# 分别留在 usv_mpc / usv_nmpc 适配器里)。
#
# 导出的 target: usv_acados::backend (产物 libusv_acados_backend.so)

if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
  set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
endif()

if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 17)
endif()
if(NOT CMAKE_CXX_STANDARD_REQUIRED)
  set(CMAKE_CXX_STANDARD_REQUIRED ON)
endif()

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(Eigen3 REQUIRED)

# ── acados 运行时 (外部预编译库, 不在此重编) ──────────────────────────
set(ACADOS_SOURCE_DIR "$ENV{ACADOS_SOURCE_DIR}")
if(NOT ACADOS_SOURCE_DIR)
  set(ACADOS_SOURCE_DIR "$ENV{HOME}/acados")
endif()
set(ACADOS_INC_DIR "${ACADOS_SOURCE_DIR}/include")
set(ACADOS_LIB_DIR "${ACADOS_SOURCE_DIR}/lib")
set(BLASFEO_INC_DIR "${ACADOS_SOURCE_DIR}/include/blasfeo/include")
set(HPIPM_INC_DIR "${ACADOS_SOURCE_DIR}/include/hpipm/include")

if(NOT EXISTS "${ACADOS_LIB_DIR}/libacados.so")
  message(FATAL_ERROR
    "未找到 acados 运行时库 (${ACADOS_LIB_DIR}/libacados.so)。"
    "请先编译安装 acados 或设置 ACADOS_SOURCE_DIR。")
endif()

# ── 两套独立生成码: 各自 STATIC + PIC, 由同一 SHARED 库私有链接 ──────
# 生成模型编号 (符号前缀/维度) 不同, 绝不能互相替代:
#   kinematic -> usv_kin_mpc_*  (nx=7)
#   dynamic   -> usv_dyn_nmpc_* (nx=8)
set(USV_ACADOS_MODELS kinematic dynamic)

set(_generated_targets "")
foreach(_model IN LISTS USV_ACADOS_MODELS)
  set(_dir "${CMAKE_CURRENT_SOURCE_DIR}/acados_generated/${_model}")
  if(_model STREQUAL "kinematic")
    set(_solver_c "${_dir}/acados_solver_usv_kin_mpc.c")
    set(_json "${_dir}/usv_kin_ocp.json")
  else()
    set(_solver_c "${_dir}/acados_solver_usv_dyn_nmpc.c")
    set(_json "${_dir}/usv_dyn_ocp.json")
  endif()
  if(NOT EXISTS "${_solver_c}")
    message(FATAL_ERROR
      "缺少 vendored acados codegen 源码 (${_solver_c})。"
      " 请用 scripts/regenerate_acados_codegen.py --model ${_model} 重新生成。")
  endif()
  file(GLOB_RECURSE _srcs "${_dir}/*.c")
  add_library(usv_acados_generated_${_model} STATIC ${_srcs})
  set_target_properties(usv_acados_generated_${_model} PROPERTIES
    C_STANDARD 99
    POSITION_INDEPENDENT_CODE ON)
  target_include_directories(usv_acados_generated_${_model} PUBLIC
    "${_dir}"
    "${ACADOS_INC_DIR}"
    "${ACADOS_INC_DIR}/acados"
    "${BLASFEO_INC_DIR}"
    "${HPIPM_INC_DIR}")
  # 生成代码的良性告警 (未用参数等只作用于生成目标, 不影响手写源码检查)
  target_compile_options(usv_acados_generated_${_model} PRIVATE -w)
  target_link_directories(usv_acados_generated_${_model} PUBLIC "${ACADOS_LIB_DIR}")
  target_link_libraries(usv_acados_generated_${_model} PUBLIC acados hpipm blasfeo m)

  # 生成清单 (逐文件路径 + 内容哈希): 供身份取证校验 install 与冻结源码一致。
  file(GLOB_RECURSE _gen_files RELATIVE "${_dir}" "${_dir}/*.c" "${_dir}/*.h" "${_dir}/*.json")
  list(SORT _gen_files)
  set(_entries "")
  foreach(_f IN LISTS _gen_files)
    file(SHA256 "${_dir}/${_f}" _hash)
    list(APPEND _entries "  {\"path\": \"${_model}/${_f}\", \"sha256\": \"${_hash}\"}")
  endforeach()
  string(REPLACE ";" ",\n" _joined "${_entries}")
  set(_manifest "${CMAKE_CURRENT_BINARY_DIR}/generated_manifest_${_model}.json")
  file(WRITE "${_manifest}" "{\n \"model\": \"${_model}\",\n \"files\": [\n${_joined}\n ]\n}\n")

  install(FILES "${_json}" "${_manifest}"
    DESTINATION share/${PROJECT_NAME}/acados_generated/${_model})
  list(APPEND _generated_targets usv_acados_generated_${_model})
endforeach()

# ── 共用求解库 ───────────────────────────────────────────────────────
add_library(usv_acados_backend SHARED
  src/acados_backend.cpp
  src/model_api.cpp
)
add_library(usv_acados::backend ALIAS usv_acados_backend)
# 导出的 IMPORTED target 名字固定为 usv_acados::usv_acados_backend; 下游统一
# 使用 IMPORTED_GLOBAL 的别名, 使 build tree 与 install tree 名字一致。
set_target_properties(usv_acados_backend PROPERTIES EXPORT_NAME backend)
target_include_directories(usv_acados_backend PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)
# 公开依赖只有 Eigen; 生成码与 acados 库是私有实现细节。
target_link_libraries(usv_acados_backend PUBLIC Eigen3::Eigen)
target_link_libraries(usv_acados_backend PRIVATE ${_generated_targets})
target_link_directories(usv_acados_backend PRIVATE "${ACADOS_LIB_DIR}")
target_link_libraries(usv_acados_backend PRIVATE acados hpipm blasfeo)

# 公共库自身的 RUNPATH 指向 acados lib (间接依赖 libacados -> libhpipm 需要)。
set_target_properties(usv_acados_backend PROPERTIES
  BUILD_RPATH "${ACADOS_LIB_DIR}"
  INSTALL_RPATH "${ACADOS_LIB_DIR}"
  VERSION 0.1.0
  SOVERSION 0
)

install(TARGETS usv_acados_backend
  EXPORT export_usv_acados
  LIBRARY DESTINATION lib
  ARCHIVE DESTINATION lib
  RUNTIME DESTINATION bin
)
install(DIRECTORY include/
  DESTINATION include
)

ament_export_targets(export_usv_acados HAS_LIBRARY_TARGET)
ament_export_include_directories(include)
ament_export_dependencies(Eigen3)

# ── 测试 ────────────────────────────────────────────────────────────
if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  # vendored 生成码 (acados_generated/) 不是手写源码, 不应受版权/风格检查。
  # 按 B 包同样的模式: linter 只对手写目录显式调用。
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

  find_package(ament_cmake_gtest REQUIRED)
  ament_add_gtest(test_instance_isolation test/test_instance_isolation.cpp)
  target_include_directories(test_instance_isolation PRIVATE
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  )
  target_link_libraries(test_instance_isolation usv_acados::backend)
  set_target_properties(test_instance_isolation PROPERTIES
    BUILD_RPATH "${CMAKE_CURRENT_BINARY_DIR};${ACADOS_LIB_DIR}")
  # RUNPATH 对间接依赖不生效, ctest 环境需追加公共库与 acados 目录。
  # 用 ENVIRONMENT_MODIFICATION 前置而不覆盖: 覆盖会丢掉 source setup.bash
  # 带来的 ROS 库路径, 测试在加载 ROS 消息库时直接 127。
  set_tests_properties(test_instance_isolation PROPERTIES ENVIRONMENT_MODIFICATION
    "LD_LIBRARY_PATH=path_list_prepend:${CMAKE_CURRENT_BINARY_DIR};LD_LIBRARY_PATH=path_list_prepend:${ACADOS_LIB_DIR}"
  )
endif()

ament_package()
