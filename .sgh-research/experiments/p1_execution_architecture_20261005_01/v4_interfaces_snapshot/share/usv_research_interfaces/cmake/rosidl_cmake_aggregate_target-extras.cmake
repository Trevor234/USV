# generated from rosidl_cmake/cmake/rosidl_cmake_aggregate_target-extras.cmake.in

# Create a convenience aggregate target usv_research_interfaces::usv_research_interfaces
# that links all generated interface targets, so downstream packages can use
# a single modern CMake target name instead of ${usv_research_interfaces_TARGETS}.
if(usv_research_interfaces_TARGETS AND NOT TARGET usv_research_interfaces::usv_research_interfaces)
  add_library(usv_research_interfaces::usv_research_interfaces INTERFACE IMPORTED)
  set_target_properties(usv_research_interfaces::usv_research_interfaces PROPERTIES
    INTERFACE_LINK_LIBRARIES "${usv_research_interfaces_TARGETS}")
endif()
