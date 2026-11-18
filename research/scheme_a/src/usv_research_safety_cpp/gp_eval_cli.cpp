// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT
//
// Lightweight C++ CLI for Python-vs-C++ numerical parity verification on `gp-snapshot-v1`.
#include <array>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>

#include <nlohmann/json.hpp>
#include "gp_predictor.hpp"

int main(int argc, char ** argv)
{
  if (argc != 3)
  {
    std::cerr << "usage: gp_eval_cli <snapshot.json> <queries.json>\n";
    return 2;
  }
  const std::string snap_path = argv[1];
  const std::string queries_path = argv[2];

  std::ifstream qifs(queries_path);
  if (!qifs)
  {
    std::cerr << "cannot open queries: " << queries_path << "\n";
    return 2;
  }
  nlohmann::json qdoc;
  qifs >> qdoc;
  const auto model = p1_gp::GpResidualModel::from_json_file(snap_path);

  nlohmann::json results = nlohmann::json::array();
  for (const auto & row : qdoc.at("queries"))
  {
    std::array<double, 5> z{
        row.at(0).get<double>(),
        row.at(1).get<double>(),
        row.at(2).get<double>(),
        row.at(3).get<double>(),
        row.at(4).get<double>(),
    };
    const auto pred = model.predict(z, true, true);
    results.push_back({
        {"mean", {pred.mean[0], pred.mean[1], pred.mean[2]}},
        {"raw_mean", {pred.raw_mean[0], pred.raw_mean[1], pred.raw_mean[2]}},
        {"std", {pred.std[0], pred.std[1], pred.std[2]}},
        {"latent_std", {pred.latent_std[0], pred.latent_std[1], pred.latent_std[2]}},
        {"nearest_std_dist", pred.nearest_std_dist},
        {"ood", pred.ood},
        {"clipped", pred.clipped},
        {"fallback_zero", pred.fallback_zero},
    });
  }
  nlohmann::json out = {
      {"snapshot_id", model.snapshot_id()},
      {"snapshot_sha256", model.snapshot_sha256()},
      {"file_sha256", model.file_sha256()},
      {"predictions", results},
  };
  std::cout << out.dump() << "\n";
  return 0;
}
