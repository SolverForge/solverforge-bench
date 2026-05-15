cmake_minimum_required(VERSION 3.18)

if(POLICY CMP0144)
  cmake_policy(SET CMP0144 NEW)
endif()

project(employee_scheduling_ortools VERSION 1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
endif()

find_package(ortools REQUIRED CONFIG)

add_executable(employee_scheduling_ortools main.cc)
target_link_libraries(employee_scheduling_ortools PRIVATE ortools::ortools)

if(ORTOOLS_ROOT)
  set_target_properties(
    employee_scheduling_ortools
    PROPERTIES BUILD_RPATH "${ORTOOLS_ROOT}/lib64"
  )
endif()
