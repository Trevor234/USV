// SPDX-License-Identifier: MIT
#pragma once
#include <rclcpp/serialization.hpp>
#include <rclcpp/serialized_message.hpp>
#include <rclcpp/message_info.hpp>
#include "p1_owned_identity.hpp"

namespace p1_observation_v4 {
// Observation of complete received typed fields. This is reserialization, not
// the original network padding, a delivery promise, or a business clock.
template<class Message>
p1_owned::Json raw_input(const Message & message, const rclcpp::MessageInfo & info,
                        const std::string & topic, const std::string & type,
                        uint64_t callback_sequence) {
  const auto entered = p1_owned::steady_ns();
  rclcpp::Serialization<Message> serializer;
  rclcpp::SerializedMessage serialized;
  serializer.serialize_message(&message, &serialized);
  const auto & cdr = serialized.get_rcl_serialized_message();
  p1_owned::require(cdr.buffer_length > 0 && cdr.buffer_length <= 1048576,
                    "callback CDR outside preregistered observation bound");
  const auto & rmw = info.get_rmw_message_info();
  const std::string bytes(reinterpret_cast<const char *>(cdr.buffer), cdr.buffer_length);
  return {{"schema", "p1-input-callback-full-cdr-v1"}, {"topic", topic},
      {"message_type", type}, {"callback_sequence", callback_sequence},
      {"entry_steady_ns", entered}, {"publisher_gid", p1_owned::gid_json(rmw.publisher_gid)},
      {"rmw_implementation", p1_owned::rmw_identifier()},
      {"source_timestamp", rmw.source_timestamp}, {"received_timestamp", rmw.received_timestamp},
      {"publication_sequence_number", rmw.publication_sequence_number},
      {"reception_sequence_number", rmw.reception_sequence_number},
      {"from_intra_process", rmw.from_intra_process}, {"cdr_bytes", cdr.buffer_length},
      {"cdr_sha256", p1_owned::sha256_bytes(bytes)},
      {"cdr_hex", p1_owned::hex(cdr.buffer, cdr.buffer_length)}};
}
}  // namespace p1_observation_v4
