cmake_minimum_required(VERSION 3.16)
project(usv_mpc_cpp LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
find_package(ament_cmake REQUIRED)
find_package(Eigen3 REQUIRED)
find_package(usv_acados REQUIRED)

# 头文件树来自 R40 的受检副本 (见 .sgh-research/.../inputs-restore/provenance.json)。
# 该包不编译任何实现：旧批次的 CMake 只把它当作 include + 依赖名的提供者。
add_library(usv_mpc_cpp INTERFACE)
# 冻结批次链接的是导入名 usv_mpc_cpp::mpc_solver_lib。这个名字必须由本包的
# 导出集合产生，不能在消费端凭空写出：给它一个真实的 INTERFACE 目标并显式命名。
add_library(usv_mpc_cpp_solver INTERFACE)
set_target_properties(usv_mpc_cpp_solver PROPERTIES EXPORT_NAME mpc_solver_lib)
target_link_libraries(usv_mpc_cpp_solver INTERFACE usv_mpc_cpp)
# 旧包导出的第二个名字：核心库（实现在 usv_nmpc::mpc_core_lib）。
add_library(usv_mpc_cpp_core INTERFACE)
set_target_properties(usv_mpc_cpp_core PROPERTIES EXPORT_NAME mpc_core_lib)
target_link_libraries(usv_mpc_cpp_core INTERFACE usv_mpc_cpp usv_nmpc::mpc_core_lib)
target_include_directories(usv_mpc_cpp INTERFACE
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
# 冻结批次直接 #include "acados_solver_usv_dyn_nmpc.h"（扁平名），所以生成码目录
# 必须也在 include 路径上；这不是新约定，是旧包安装布局的一部分。
target_include_directories(usv_mpc_cpp INTERFACE
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include/usv_mpc_cpp/acados_generated>
  $<INSTALL_INTERFACE:include/usv_mpc_cpp/acados_generated>)
# acados 的公共头（acados/utils/types.h 等）不在 usv_acados 的导出面里：生成码
# 是私有实现细节，但旧包把它当公共头发出，消费端因此需要这条路径。
if(DEFINED ENV{ACADOS_SOURCE_DIR})
  target_include_directories(usv_mpc_cpp INTERFACE
    $ENV{ACADOS_SOURCE_DIR}/include
    $ENV{ACADOS_SOURCE_DIR}/include/blasfeo/include
    $ENV{ACADOS_SOURCE_DIR}/include/hpipm/include
    $ENV{ACADOS_SOURCE_DIR}/interfaces/acados_c)
else()
  message(FATAL_ERROR "ACADOS_SOURCE_DIR is required to export the generated headers")
endif()
find_package(usv_nmpc REQUIRED)
target_link_libraries(usv_mpc_cpp INTERFACE Eigen3::Eigen usv_acados::backend usv_nmpc::mpc_solver_lib)

install(DIRECTORY include/ DESTINATION include)
install(TARGETS usv_mpc_cpp usv_mpc_cpp_solver usv_mpc_cpp_core EXPORT usv_mpc_cpp_targets)
ament_export_targets(usv_mpc_cpp_targets HAS_LIBRARY_TARGET)
ament_export_include_directories(include)
ament_export_dependencies(Eigen3 usv_acados usv_nmpc)
find_package(OpenSSL REQUIRED)
find_package(Threads REQUIRED)
target_link_libraries(usv_mpc_cpp INTERFACE OpenSSL::Crypto Threads::Threads)
if(DEFINED ENV{ACADOS_SOURCE_DIR})
  # 旧包把 acados 作为公共链接依赖发出；冻结的测试直接引用 ocp_nlp_* 符号。
  target_link_libraries(usv_mpc_cpp INTERFACE
    "$ENV{ACADOS_SOURCE_DIR}/lib/libacados.so"
    "$ENV{ACADOS_SOURCE_DIR}/lib/libblasfeo.so"
    "$ENV{ACADOS_SOURCE_DIR}/lib/libhpipm.so")
endif()
ament_export_dependencies(OpenSSL Threads)
ament_package()
