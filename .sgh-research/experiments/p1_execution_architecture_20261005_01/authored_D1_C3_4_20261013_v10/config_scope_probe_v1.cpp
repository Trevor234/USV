// Dedicated offline probe. Functions in the generated include are copied
// verbatim from the pinned current common header; no runtime hook is built.
#include <nlohmann/json.hpp>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
using Json = nlohmann::json;
inline void require(bool value, const std::string &message) {
  if (!value) throw std::runtime_error(message);
}
#include "current_canonical_functions.inc"

int main() {
  try {
    std::string line;
    while (std::getline(std::cin, line)) {
      const auto input = Json::parse(line);
      Json output = Json::object();
      if (input.contains("parameters")) {
        Json rows = input.at("parameters");
        for (auto it = rows.begin(); it != rows.end(); ++it) {
          const auto kind = it.value().at("type").get<int>();
          auto &row = it.value();
          if (kind == 3) row["canonical_value"] = double_canonical(row.at("value").get<double>());
          else if (kind == 8) {
            Json bits = Json::array();
            for (const auto &value : row.at("value")) bits.push_back(double_canonical(value.get<double>()));
            row["canonical_value"] = bits;
          } else row["canonical_value"] = row.at("value");
        }
        output["canonical_dump"] = canonical_parameters(rows).dump();
      }
      if (input.contains("ieee_bits")) {
        Json tokens = Json::array();
        for (const auto &item : input.at("ieee_bits")) {
          const auto bits = std::stoull(item.get<std::string>(), nullptr, 16);
          double value;
          static_assert(sizeof(value) == sizeof(bits));
          std::memcpy(&value, &bits, sizeof(value));
          require(std::isfinite(value), "probe nonfinite input");
          tokens.push_back(Json(value).dump());
        }
        output["tokens"] = tokens;
      }
      std::cout << output.dump() << '\n';
    }
    return 0;
  } catch (const std::exception &error) {
    std::cerr << error.what() << '\n';
    return 2;
  }
}
