// SPDX-License-Identifier: MIT
// Pure validator process: no ROS, threads, solver, output topic, or actuator API.
#include "p1_full_contract.hpp"
#include <fstream>
#include <iostream>

int main() {
  std::string line;
  while (std::getline(std::cin, line)) {
    nlohmann::json result;
    try {
      const auto request = nlohmann::json::parse(line);
      std::ifstream in(request.at("path").get<std::string>(), std::ios::binary);
      if (!in) throw std::runtime_error("contract file unavailable");
      std::string text(65537, '\0');
      in.read(text.data(), text.size());text.resize(size_t(in.gcount()));
      const auto c = p1::parse_unique_contract(text);
      const auto action = request.at("action").get<std::string>();
      if (action == "fields") p1::validate_contract_fields(c);
      else if (action == "mode") p1::validate_contract_mode(c, request.at("mode"));
      else if (action == "runtime") p1::require_runtime_contract_mode(c, request.at("mode"));
      else throw std::runtime_error("unknown probe action");
      result = {{"accepted", true}, {"fields", c.size()}};
    } catch (const std::exception & e) {
      result = {{"accepted", false}, {"reason", e.what()}};
    }
    result["spec_sha256"] = p1::full_contract_spec_sha256;
    result["profile_id"] = p1::contract_parameter_profile;
    result["physical_execute_release_enabled"] = p1::physical_execute_release_enabled;
    std::cout << result.dump() << std::endl;
  }
}
