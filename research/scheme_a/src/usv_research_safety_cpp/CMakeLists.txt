cmake_minimum_required(VERSION 3.16)
project(usv_research_safety_cpp)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(usv_nmpc REQUIRED)
find_package(usv_research_interfaces REQUIRED)
find_package(nav_msgs REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(std_msgs REQUIRED)
find_package(rosgraph_msgs REQUIRED)
find_package(mavros_msgs REQUIRED)
find_package(Eigen3 REQUIRED)
find_package(nlohmann_json REQUIRED)
find_package(OpenSSL REQUIRED)
find_package(usv_acados REQUIRED)
find_package(Threads REQUIRED)
# 单一 capsule 的所有者：事务层 + 引擎会话。后端不再经 mpc_solver_lib 的
# 回退封装进入，因为回退会把失败变成"看起来成功"。
add_library(p1_model_runtime STATIC
  src/p1_model_reference.cpp
  src/p1_model_transaction.cpp
  src/p1_engine_session.cpp
  src/p1_worker_engine.cpp
  src/gp_predictor.cpp
  src/p1_gp_snapshot.cpp
)
target_include_directories(p1_model_runtime PUBLIC . ${CMAKE_CURRENT_SOURCE_DIR}/src)
target_link_libraries(p1_model_runtime PUBLIC usv_acados::backend usv_nmpc::mpc_core_lib
  Eigen3::Eigen OpenSSL::Crypto nlohmann_json::nlohmann_json Threads::Threads)

add_executable(p1_solver_worker solver_worker.cpp)
target_include_directories(p1_solver_worker PRIVATE . ${CMAKE_CURRENT_SOURCE_DIR}/src)
target_link_libraries(p1_solver_worker p1_model_runtime OpenSSL::Crypto Threads::Threads nlohmann_json::nlohmann_json)
ament_target_dependencies(p1_solver_worker rclcpp usv_research_interfaces)
# 进程内测试接缝只在测试/故障构建中存在：普通构建编译剔除，也不接受相关参数。
# 闭环故障注入（延迟、迟到、重复、hold 到期）不在这一类，它编入普通二进制，
# 但受合同 controlled_sim_faults_enabled 门控。
option(USV_RESEARCH_TEST_SEAMS "Build in-process Worker test seams" OFF)
if(USV_RESEARCH_TEST_SEAMS)
  # 受控仿真的反证刺激需要 worker 侧"原生求解前阻塞"这一注入点；它只在
  # 显式开关下编译，且运行期还要合同里的 controlled_sim_faults_enabled 才生效。
  target_compile_definitions(p1_solver_worker PRIVATE USV_RESEARCH_TEST_SEAMS)
endif()
set_target_properties(p1_solver_worker PROPERTIES
  INSTALL_RPATH "$ENV{HOME}/acados/lib"
  INSTALL_RPATH_USE_LINK_PATH TRUE)
install(TARGETS p1_solver_worker DESTINATION lib/${PROJECT_NAME})
if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/regulator.cpp")
 add_executable(p1_regulator regulator.cpp)
 target_include_directories(p1_regulator PRIVATE . ${CMAKE_CURRENT_SOURCE_DIR}/src ${CMAKE_CURRENT_SOURCE_DIR}/plant)
 target_link_libraries(p1_regulator p1_model_runtime usv_nmpc::mpc_core_lib OpenSSL::Crypto Threads::Threads nlohmann_json::nlohmann_json)
 ament_target_dependencies(p1_regulator rclcpp usv_research_interfaces nav_msgs sensor_msgs std_msgs rosgraph_msgs mavros_msgs)
 install(TARGETS p1_regulator DESTINATION lib/${PROJECT_NAME})
endif()
add_executable(p1_gp_eval_cli gp_eval_cli.cpp src/gp_predictor.cpp)
target_include_directories(p1_gp_eval_cli PRIVATE . ${CMAKE_CURRENT_SOURCE_DIR}/src)
target_link_libraries(p1_gp_eval_cli OpenSSL::Crypto nlohmann_json::nlohmann_json)
ament_target_dependencies(p1_gp_eval_cli usv_research_interfaces)
install(TARGETS p1_gp_eval_cli DESTINATION lib/${PROJECT_NAME})

add_executable(p1_contract_validate contract_validate_cli.cpp)
target_include_directories(p1_contract_validate PRIVATE . ${CMAKE_CURRENT_SOURCE_DIR}/src)
target_link_libraries(p1_contract_validate usv_nmpc::mpc_core_lib OpenSSL::Crypto nlohmann_json::nlohmann_json)
ament_target_dependencies(p1_contract_validate usv_research_interfaces)
install(TARGETS p1_contract_validate DESTINATION lib/${PROJECT_NAME})
if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/plant/p1_x86_plant.cpp")
 add_executable(p1_x86_plant plant/p1_x86_plant.cpp)
 target_include_directories(p1_x86_plant PRIVATE . ${CMAKE_CURRENT_SOURCE_DIR}/src ${CMAKE_CURRENT_SOURCE_DIR}/plant)
 target_link_libraries(p1_x86_plant usv_nmpc::mpc_core_lib OpenSSL::Crypto Threads::Threads nlohmann_json::nlohmann_json)
 ament_target_dependencies(p1_x86_plant rclcpp usv_research_interfaces nav_msgs sensor_msgs rosgraph_msgs)
 install(TARGETS p1_x86_plant DESTINATION lib/${PROJECT_NAME})
endif()
if(BUILD_TESTING)
 find_package(ament_cmake_gtest REQUIRED)
 find_package(ament_cmake_pytest REQUIRED)
 ament_add_gtest(test_p1_full_contract test_p1_full_contract.cpp)
 target_include_directories(test_p1_full_contract PRIVATE . ${CMAKE_CURRENT_SOURCE_DIR}/src)
 target_link_libraries(test_p1_full_contract nlohmann_json::nlohmann_json)

 ament_add_gtest(test_p1_admission test_p1_admission.cpp)
 target_include_directories(test_p1_admission PRIVATE . ${CMAKE_CURRENT_SOURCE_DIR}/src)
 target_link_libraries(test_p1_admission usv_nmpc::mpc_core_lib)
 ament_add_gtest(test_p1_worker_liveness test_p1_worker_liveness.cpp)
 target_include_directories(test_p1_worker_liveness PRIVATE . ${CMAKE_CURRENT_SOURCE_DIR}/src)
 ament_add_gtest(test_p1_preparation_barrier test_p1_preparation_barrier.cpp)
 target_include_directories(test_p1_preparation_barrier PRIVATE . ${CMAKE_CURRENT_SOURCE_DIR}/src)
 ament_add_gtest(test_p1_capability_lease test_p1_capability_lease.cpp)
 target_include_directories(test_p1_capability_lease PRIVATE . ${CMAKE_CURRENT_SOURCE_DIR}/src)
 ament_add_gtest(test_p1_tick_barrier test_p1_tick_barrier.cpp)
 target_include_directories(test_p1_tick_barrier PRIVATE . ${CMAKE_CURRENT_SOURCE_DIR}/src)
 # 这个测试需要在"事务提交后、真实准备前"插入一段可数等待，才能证明准备期间
 # 越过原始 deadline。接缝只存在于本测试目标（编译剔除于普通库与二进制）。
 ament_add_gtest(test_p1_engine_session test_p1_engine_session.cpp
   src/p1_model_reference.cpp src/p1_model_transaction.cpp
   src/p1_engine_session.cpp src/p1_worker_engine.cpp)
 target_include_directories(test_p1_engine_session PRIVATE . ${CMAKE_CURRENT_SOURCE_DIR}/src)
 target_compile_definitions(test_p1_engine_session PRIVATE USV_RESEARCH_TEST_SEAMS)
 target_link_libraries(test_p1_engine_session usv_acados::backend usv_nmpc::mpc_core_lib
   Eigen3::Eigen OpenSSL::Crypto nlohmann_json::nlohmann_json Threads::Threads)

 # 步骤 2 的确定性测试：物理内核 / 执行准入 / 回执锚点。全部 ROS-free。
 ament_add_gtest(test_p1_plant_core test_p1_plant_core.cpp)
 target_include_directories(test_p1_plant_core PRIVATE . ${CMAKE_CURRENT_SOURCE_DIR}/src ${CMAKE_CURRENT_SOURCE_DIR}/plant)
 target_link_libraries(test_p1_plant_core usv_nmpc::mpc_core_lib Eigen3::Eigen)

 ament_add_gtest(test_gp_predictor test_gp_predictor.cpp src/gp_predictor.cpp)
 target_include_directories(test_gp_predictor PRIVATE . ${CMAKE_CURRENT_SOURCE_DIR}/src)
 target_link_libraries(test_gp_predictor OpenSSL::Crypto nlohmann_json::nlohmann_json)
 ament_target_dependencies(test_gp_predictor usv_research_interfaces)

 ament_add_gtest(test_p1_gp_snapshot test_p1_gp_snapshot.cpp src/gp_predictor.cpp src/p1_gp_snapshot.cpp)
 target_include_directories(test_p1_gp_snapshot PRIVATE . ${CMAKE_CURRENT_SOURCE_DIR}/src)
 target_link_libraries(test_p1_gp_snapshot usv_nmpc::mpc_core_lib Eigen3::Eigen OpenSSL::Crypto nlohmann_json::nlohmann_json)

 ament_add_gtest(test_p1_plant_admission test_p1_plant_admission.cpp)
 target_include_directories(test_p1_plant_admission PRIVATE . ${CMAKE_CURRENT_SOURCE_DIR}/src ${CMAKE_CURRENT_SOURCE_DIR}/plant)
 target_link_libraries(test_p1_plant_admission usv_nmpc::mpc_core_lib Eigen3::Eigen)

 ament_add_gtest(test_p1_receipt_anchor test_p1_receipt_anchor.cpp)
 target_include_directories(test_p1_receipt_anchor PRIVATE . ${CMAKE_CURRENT_SOURCE_DIR}/src ${CMAKE_CURRENT_SOURCE_DIR}/plant)
 target_link_libraries(test_p1_receipt_anchor usv_nmpc::mpc_core_lib Eigen3::Eigen)

 ament_add_gtest(test_p1_resources test_p1_resources.cpp)
 target_include_directories(test_p1_resources PRIVATE . ${CMAKE_CURRENT_SOURCE_DIR}/src)
 target_link_libraries(test_p1_resources nlohmann_json::nlohmann_json)
 ament_target_dependencies(test_p1_resources rclcpp usv_research_interfaces nav_msgs std_msgs)
 ament_add_pytest_test(test_p1_plant_receipts test_p1_plant_receipts.py)
 ament_add_pytest_test(test_capture_scheme_a_baseline test_capture_scheme_a_baseline.py)
 ament_add_pytest_test(test_scheme_a_controlled_sim test_scheme_a_controlled_sim.py)

 # 时钟断档诊断：缓冲/排他创建/summary 的确定性回归，以及诊断器对证据形状的判据。
 ament_add_gtest(test_p1_clock_diagnostics test_p1_clock_diagnostics.cpp)
 target_include_directories(test_p1_clock_diagnostics PRIVATE . ${CMAKE_CURRENT_SOURCE_DIR}/src)
 target_link_libraries(test_p1_clock_diagnostics nlohmann_json::nlohmann_json)

 ament_add_pytest_test(test_scheme_a_clock_gap test_scheme_a_clock_gap.py)

 # 实船调试服务接管：合同 profile + 有限状态机（注入整数单调时钟，ROS-free）
 ament_add_gtest(test_p1_shipboard_commissioning test_p1_shipboard_commissioning.cpp)
 target_include_directories(test_p1_shipboard_commissioning PRIVATE . ${CMAKE_CURRENT_SOURCE_DIR}/src)
 target_link_libraries(test_p1_shipboard_commissioning nlohmann_json::nlohmann_json)
 ament_add_pytest_test(test_shipboard_commissioning test_shipboard_commissioning.py)
 ament_add_pytest_test(test_p1_commissioning_checker test_p1_commissioning_checker.py)
endif()
install(DIRECTORY launch DESTINATION share/${PROJECT_NAME})
install(DIRECTORY model DESTINATION share/${PROJECT_NAME})
# PROGRAMS：监督器与 checker 由 launch / 维护 driver 以绝对路径调用。
install(PROGRAMS
  scripts/run_shipboard_commissioning.py
  scripts/check_shipboard_commissioning.py
  DESTINATION lib/${PROJECT_NAME})
ament_package()
