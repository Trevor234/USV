#include "p1_witness.hpp"
#include <iostream>
int main(){constexpr auto l=p1::Witness::layout();
  std::cout<<"{\"header_bytes\":"<<l.header_bytes<<",\"first_failure_payload_bytes\":"<<l.first_failure_payload_bytes
    <<",\"tick_payload_bytes\":"<<l.tick_payload_bytes<<",\"submit_payload_bytes\":"<<l.submit_payload_bytes<<",\"activation_payload_bytes\":"<<l.activation_payload_bytes<<",\"phase_payload_bytes\":"<<l.phase_payload_bytes
    <<",\"tick_slot_bytes\":"<<l.tick_slot_bytes<<",\"submit_slot_bytes\":"<<l.submit_slot_bytes<<",\"activation_slot_bytes\":"<<l.activation_slot_bytes<<",\"phase_slot_bytes\":"<<l.phase_slot_bytes
    <<",\"tick_stream_bytes\":"<<l.tick_stream_bytes<<",\"submit_stream_bytes\":"<<l.submit_stream_bytes<<",\"activation_stream_bytes\":"<<l.activation_stream_bytes<<",\"phase_stream_bytes\":"<<l.phase_stream_bytes<<",\"total_bytes\":"<<l.total_bytes<<"}\n";
}
