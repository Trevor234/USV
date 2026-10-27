// generated from rosidl_generator_c/resource/idl__functions.h.em
// with input from usv_research_interfaces:msg/ReferencePrediction.idl
// generated code does not contain a copyright notice

// IWYU pragma: private, include "usv_research_interfaces/msg/reference_prediction.h"


#ifndef USV_RESEARCH_INTERFACES__MSG__DETAIL__REFERENCE_PREDICTION__FUNCTIONS_H_
#define USV_RESEARCH_INTERFACES__MSG__DETAIL__REFERENCE_PREDICTION__FUNCTIONS_H_

#ifdef __cplusplus
extern "C"
{
#endif

#include <stdbool.h>
#include <stdlib.h>

#include "rosidl_runtime_c/action_type_support_struct.h"
#include "rosidl_runtime_c/message_type_support_struct.h"
#include "rosidl_runtime_c/service_type_support_struct.h"
#include "rosidl_runtime_c/type_description/type_description__struct.h"
#include "rosidl_runtime_c/type_description/type_source__struct.h"
#include "rosidl_runtime_c/type_hash.h"
#include "rosidl_runtime_c/visibility_control.h"
#include "usv_research_interfaces/msg/rosidl_generator_c__visibility_control.h"

#include "usv_research_interfaces/msg/detail/reference_prediction__struct.h"

/// Initialize msg/ReferencePrediction message.
/**
 * If the init function is called twice for the same message without
 * calling fini inbetween previously allocated memory will be leaked.
 * \param[in,out] msg The previously allocated message pointer.
 * Fields without a default value will not be initialized by this function.
 * You might want to call memset(msg, 0, sizeof(
 * usv_research_interfaces__msg__ReferencePrediction
 * )) before or use
 * usv_research_interfaces__msg__ReferencePrediction__create()
 * to allocate and initialize the message.
 * \return true if initialization was successful, otherwise false
 */
ROSIDL_GENERATOR_C_PUBLIC_usv_research_interfaces
bool
usv_research_interfaces__msg__ReferencePrediction__init(usv_research_interfaces__msg__ReferencePrediction * msg);

/// Finalize msg/ReferencePrediction message.
/**
 * \param[in,out] msg The allocated message pointer.
 */
ROSIDL_GENERATOR_C_PUBLIC_usv_research_interfaces
void
usv_research_interfaces__msg__ReferencePrediction__fini(usv_research_interfaces__msg__ReferencePrediction * msg);

/// Create msg/ReferencePrediction message.
/**
 * It allocates the memory for the message, sets the memory to zero, and
 * calls
 * usv_research_interfaces__msg__ReferencePrediction__init().
 * \return The pointer to the initialized message if successful,
 * otherwise NULL
 */
ROSIDL_GENERATOR_C_PUBLIC_usv_research_interfaces
usv_research_interfaces__msg__ReferencePrediction *
usv_research_interfaces__msg__ReferencePrediction__create(void);

/// Destroy msg/ReferencePrediction message.
/**
 * It calls
 * usv_research_interfaces__msg__ReferencePrediction__fini()
 * and frees the memory of the message.
 * \param[in,out] msg The allocated message pointer.
 */
ROSIDL_GENERATOR_C_PUBLIC_usv_research_interfaces
void
usv_research_interfaces__msg__ReferencePrediction__destroy(usv_research_interfaces__msg__ReferencePrediction * msg);

/// Check for msg/ReferencePrediction message equality.
/**
 * \param[in] lhs The message on the left hand size of the equality operator.
 * \param[in] rhs The message on the right hand size of the equality operator.
 * \return true if messages are equal, otherwise false.
 */
ROSIDL_GENERATOR_C_PUBLIC_usv_research_interfaces
bool
usv_research_interfaces__msg__ReferencePrediction__are_equal(const usv_research_interfaces__msg__ReferencePrediction * lhs, const usv_research_interfaces__msg__ReferencePrediction * rhs);

/// Copy a msg/ReferencePrediction message.
/**
 * This functions performs a deep copy, as opposed to the shallow copy that
 * plain assignment yields.
 *
 * \param[in] input The source message pointer.
 * \param[out] output The target message pointer, which must
 *   have been initialized before calling this function.
 * \return true if successful, or false if either pointer is null
 *   or memory allocation fails.
 */
ROSIDL_GENERATOR_C_PUBLIC_usv_research_interfaces
bool
usv_research_interfaces__msg__ReferencePrediction__copy(
  const usv_research_interfaces__msg__ReferencePrediction * input,
  usv_research_interfaces__msg__ReferencePrediction * output);

/// Retrieve pointer to the hash of the description of this type.
ROSIDL_GENERATOR_C_PUBLIC_usv_research_interfaces
const rosidl_type_hash_t *
usv_research_interfaces__msg__ReferencePrediction__get_type_hash(
  const rosidl_message_type_support_t * type_support);

/// Retrieve pointer to the description of this type.
ROSIDL_GENERATOR_C_PUBLIC_usv_research_interfaces
const rosidl_runtime_c__type_description__TypeDescription *
usv_research_interfaces__msg__ReferencePrediction__get_type_description(
  const rosidl_message_type_support_t * type_support);

/// Retrieve pointer to the single raw source text that defined this type.
ROSIDL_GENERATOR_C_PUBLIC_usv_research_interfaces
const rosidl_runtime_c__type_description__TypeSource *
usv_research_interfaces__msg__ReferencePrediction__get_individual_type_description_source(
  const rosidl_message_type_support_t * type_support);

/// Retrieve pointer to the recursive raw sources that defined the description of this type.
ROSIDL_GENERATOR_C_PUBLIC_usv_research_interfaces
const rosidl_runtime_c__type_description__TypeSource__Sequence *
usv_research_interfaces__msg__ReferencePrediction__get_type_description_sources(
  const rosidl_message_type_support_t * type_support);

/// Initialize array of msg/ReferencePrediction messages.
/**
 * It allocates the memory for the number of elements and calls
 * usv_research_interfaces__msg__ReferencePrediction__init()
 * for each element of the array.
 * \param[in,out] array The allocated array pointer.
 * \param[in] size The size / capacity of the array.
 * \return true if initialization was successful, otherwise false
 * If the array pointer is valid and the size is zero it is guaranteed
 # to return true.
 */
ROSIDL_GENERATOR_C_PUBLIC_usv_research_interfaces
bool
usv_research_interfaces__msg__ReferencePrediction__Sequence__init(usv_research_interfaces__msg__ReferencePrediction__Sequence * array, size_t size);

/// Finalize array of msg/ReferencePrediction messages.
/**
 * It calls
 * usv_research_interfaces__msg__ReferencePrediction__fini()
 * for each element of the array and frees the memory for the number of
 * elements.
 * \param[in,out] array The initialized array pointer.
 */
ROSIDL_GENERATOR_C_PUBLIC_usv_research_interfaces
void
usv_research_interfaces__msg__ReferencePrediction__Sequence__fini(usv_research_interfaces__msg__ReferencePrediction__Sequence * array);

/// Create array of msg/ReferencePrediction messages.
/**
 * It allocates the memory for the array and calls
 * usv_research_interfaces__msg__ReferencePrediction__Sequence__init().
 * \param[in] size The size / capacity of the array.
 * \return The pointer to the initialized array if successful, otherwise NULL
 */
ROSIDL_GENERATOR_C_PUBLIC_usv_research_interfaces
usv_research_interfaces__msg__ReferencePrediction__Sequence *
usv_research_interfaces__msg__ReferencePrediction__Sequence__create(size_t size);

/// Destroy array of msg/ReferencePrediction messages.
/**
 * It calls
 * usv_research_interfaces__msg__ReferencePrediction__Sequence__fini()
 * on the array,
 * and frees the memory of the array.
 * \param[in,out] array The initialized array pointer.
 */
ROSIDL_GENERATOR_C_PUBLIC_usv_research_interfaces
void
usv_research_interfaces__msg__ReferencePrediction__Sequence__destroy(usv_research_interfaces__msg__ReferencePrediction__Sequence * array);

/// Check for msg/ReferencePrediction message array equality.
/**
 * \param[in] lhs The message array on the left hand size of the equality operator.
 * \param[in] rhs The message array on the right hand size of the equality operator.
 * \return true if message arrays are equal in size and content, otherwise false.
 */
ROSIDL_GENERATOR_C_PUBLIC_usv_research_interfaces
bool
usv_research_interfaces__msg__ReferencePrediction__Sequence__are_equal(const usv_research_interfaces__msg__ReferencePrediction__Sequence * lhs, const usv_research_interfaces__msg__ReferencePrediction__Sequence * rhs);

/// Copy an array of msg/ReferencePrediction messages.
/**
 * This functions performs a deep copy, as opposed to the shallow copy that
 * plain assignment yields.
 *
 * \param[in] input The source array pointer.
 * \param[out] output The target array pointer, which must
 *   have been initialized before calling this function.
 * \return true if successful, or false if either pointer
 *   is null or memory allocation fails.
 */
ROSIDL_GENERATOR_C_PUBLIC_usv_research_interfaces
bool
usv_research_interfaces__msg__ReferencePrediction__Sequence__copy(
  const usv_research_interfaces__msg__ReferencePrediction__Sequence * input,
  usv_research_interfaces__msg__ReferencePrediction__Sequence * output);

#ifdef __cplusplus
}
#endif

#endif  // USV_RESEARCH_INTERFACES__MSG__DETAIL__REFERENCE_PREDICTION__FUNCTIONS_H_
