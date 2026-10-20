cmake_minimum_required(VERSION 3.8)
project(usv_research_interfaces)
find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/StateSnapshot.msg" "msg/AppliedControl.msg" "msg/CycleTiming.msg" "msg/ReferencePrediction.msg"
  "msg/SolveJob.msg" "msg/SolveCandidate.msg" "msg/WorkerCapability.msg" "msg/ExecutionDecision.msg")
# P0_REFERENCE_PREDICTION_V1
ament_export_dependencies(rosidl_default_runtime)
ament_package()
