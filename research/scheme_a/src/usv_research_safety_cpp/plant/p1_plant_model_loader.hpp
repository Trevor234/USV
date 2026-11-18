// Copyright 2026 USV Developer
// SPDX-License-Identifier: MIT
//
// Helper for loading optional plant_actual hydrodynamic parameters and enforcing
// strict physical / SPD inertia bounds before entering simulation spin.
#pragma once

#include <cmath>
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <string>

#include "p1_resources.hpp"
#include "usv_nmpc/usv_model_dynamic.hpp"

namespace p1_plant
{

struct HydroLoadResult
{
  usv_mpc::HydroParams controller_nominal{};
  usv_mpc::HydroParams plant_actual{};
  std::string source_path;
  bool overridden = false;
};

inline nlohmann::json hydro_to_json(const usv_mpc::HydroParams & h)
{
  return nlohmann::json{
      {"mass", h.mass},
      {"Iz", h.Iz},
      {"xg", h.xg},
      {"d_thruster", h.d_thruster},
      {"Xu_dot", h.Xu_dot},
      {"Yv_dot", h.Yv_dot},
      {"Yr_dot", h.Yr_dot},
      {"Nv_dot", h.Nv_dot},
      {"Nr_dot", h.Nr_dot},
      {"Xu", h.Xu},
      {"Yv", h.Yv},
      {"Yr", h.Yr},
      {"Nv", h.Nv},
      {"Nr", h.Nr},
      {"Xuu", h.Xuu},
      {"Yvv", h.Yvv},
      {"Yrr", h.Yrr},
      {"Nvv", h.Nvv},
      {"Nrr", h.Nrr},
  };
}

inline void validate_hydro_params(const usv_mpc::HydroParams & h, const std::string & label)
{
  const double all[] = {
      h.mass, h.Iz, h.xg, h.d_thruster,
      h.Xu_dot, h.Yv_dot, h.Yr_dot, h.Nv_dot, h.Nr_dot,
      h.Xu, h.Yv, h.Yr, h.Nv, h.Nr,
      h.Xuu, h.Yvv, h.Yrr, h.Nvv, h.Nrr};
  for (double val : all)
  {
    if (!std::isfinite(val))
    {
      throw std::runtime_error(label + ": non_finite_hydro_param");
    }
  }
  if (h.mass <= 0.0 || h.Iz <= 0.0 || h.d_thruster <= 0.0)
  {
    throw std::runtime_error(label + ": invalid_physical_scale (mass, Iz, d_thruster must be > 0)");
  }

  // Fossen rigid-body + added mass inertia matrix M:
  //   [ m - Xu_dot,          0,                 0        ]
  //   [     0,        m - Yv_dot,       m*xg - Yr_dot    ]
  //   [     0,        m*xg - Nv_dot,    Iz - Nr_dot      ]
  const double m11 = h.mass - h.Xu_dot;
  const double m22 = h.mass - h.Yv_dot;
  const double m23 = h.mass * h.xg - h.Yr_dot;
  const double m32 = h.mass * h.xg - h.Nv_dot;
  const double m33 = h.Iz - h.Nr_dot;
  const double m23_sym = 0.5 * (m23 + m32);
  const double det_2x2 = m22 * m33 - m23 * m32;
  const double det_sym = m22 * m33 - m23_sym * m23_sym;

  if (m11 <= 0.0 || m22 <= 0.0 || m33 <= 0.0 || det_2x2 <= 0.0 || det_sym <= 0.0)
  {
    std::ostringstream oss;
    oss << label << ": mass_matrix_not_spd (m11=" << m11 << ", m22=" << m22
        << ", m33=" << m33 << ", det=" << det_2x2 << ", det_sym=" << det_sym << ")";
    throw std::runtime_error(oss.str());
  }

  // Diagonal hydrodynamic damping must oppose motion (non-positive Fossen coefficients).
  if (h.Xu > 0.0 || h.Yv > 0.0 || h.Nr > 0.0 ||
      h.Xuu > 0.0 || h.Yvv > 0.0 || h.Nrr > 0.0)
  {
    throw std::runtime_error(
        label + ": invalid_damping_sign (Xu, Yv, Nr, Xuu, Yvv, Nrr must be <= 0)");
  }
}

inline void apply_hydro_overrides(usv_mpc::HydroParams & target, const nlohmann::json & obj)
{
  if (!obj.is_object())
  {
    throw std::runtime_error("plant_actual hydro override must be a JSON object");
  }
  auto maybe_set = [&](const char * key, double & field) {
    if (!obj.contains(key)) return;
    const auto & v = obj.at(key);
    if (!v.is_number())
    {
      throw std::runtime_error(std::string("non-numeric hydro override key: ") + key);
    }
    field = v.get<double>();
  };
  maybe_set("mass", target.mass);
  maybe_set("Iz", target.Iz);
  maybe_set("xg", target.xg);
  maybe_set("d_thruster", target.d_thruster);
  maybe_set("Xu_dot", target.Xu_dot);
  maybe_set("Yv_dot", target.Yv_dot);
  maybe_set("Yr_dot", target.Yr_dot);
  maybe_set("Nv_dot", target.Nv_dot);
  maybe_set("Nr_dot", target.Nr_dot);
  maybe_set("Xu", target.Xu);
  maybe_set("Yv", target.Yv);
  maybe_set("Yr", target.Yr);
  maybe_set("Nv", target.Nv);
  maybe_set("Nr", target.Nr);
  maybe_set("Xuu", target.Xuu);
  maybe_set("Yvv", target.Yvv);
  maybe_set("Yrr", target.Yrr);
  maybe_set("Nvv", target.Nvv);
  maybe_set("Nrr", target.Nrr);
}

inline HydroLoadResult load_plant_hydro(
    const usv_mpc::HydroParams & controller_nominal,
    const std::string & plant_model_file)
{
  validate_hydro_params(controller_nominal, "controller_nominal");
  HydroLoadResult result;
  result.controller_nominal = controller_nominal;
  result.plant_actual = controller_nominal;
  result.source_path = plant_model_file;
  result.overridden = !plant_model_file.empty();

  if (plant_model_file.empty())
  {
    return result;
  }

  std::ifstream ifs(plant_model_file);
  if (!ifs)
  {
    throw std::runtime_error("plant_model_file unreadable: " + plant_model_file);
  }
  nlohmann::json doc;
  ifs >> doc;
  if (!doc.is_object())
  {
    throw std::runtime_error("plant_model_file must contain a JSON object");
  }
  const nlohmann::json & section =
      doc.contains("plant_actual")
          ? doc.at("plant_actual")
          : (doc.contains("hydro") ? doc.at("hydro") : doc);
  apply_hydro_overrides(result.plant_actual, section);
  validate_hydro_params(result.plant_actual, "plant_actual");
  return result;
}

}  // namespace p1_plant
