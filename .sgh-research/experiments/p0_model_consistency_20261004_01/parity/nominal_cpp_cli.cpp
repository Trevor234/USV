// Independent test driver. Compiles the actual workspace model source unchanged.
#include <cmath>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
#include <nlohmann/json.hpp>
#include "usv_mpc_cpp/usv_model_dynamic.hpp"

using json=nlohmann::json;
using usv_mpc::HydroParams;
using usv_mpc::USVDynamicModel;
using usv_mpc::Vector6d;

static HydroParams parse_params(const json & j) {
  HydroParams p;
#define PARAM(name) p.name=j.at(#name).get<double>(); if (!std::isfinite(p.name)) {throw std::runtime_error("nonfinite parameter " #name);}
  PARAM(mass) PARAM(Iz) PARAM(xg) PARAM(d_thruster)
  PARAM(Xu_dot) PARAM(Yv_dot) PARAM(Yr_dot) PARAM(Nv_dot) PARAM(Nr_dot)
  PARAM(Xu) PARAM(Yv) PARAM(Yr) PARAM(Nv) PARAM(Nr)
  PARAM(Xuu) PARAM(Yvv) PARAM(Yrr) PARAM(Nvv) PARAM(Nrr)
#undef PARAM
  return p;
}

static json dump_params(const HydroParams & p) {
  json j;
#define PARAM(name) j[#name]=p.name;
  PARAM(mass) PARAM(Iz) PARAM(xg) PARAM(d_thruster)
  PARAM(Xu_dot) PARAM(Yv_dot) PARAM(Yr_dot) PARAM(Nv_dot) PARAM(Nr_dot)
  PARAM(Xu) PARAM(Yv) PARAM(Yr) PARAM(Nv) PARAM(Nr)
  PARAM(Xuu) PARAM(Yvv) PARAM(Yrr) PARAM(Nvv) PARAM(Nrr)
#undef PARAM
  return j;
}

static Vector6d parse_state(const json & j) {
  if (!j.is_array() || j.size()!=6) {throw std::runtime_error("state requires six values");}
  Vector6d x;
  for (int i=0;i<6;++i) {x(i)=j.at(i).get<double>();}
  if (!x.allFinite()) {throw std::runtime_error("nonfinite state");}
  return x;
}

static Eigen::Vector2d parse_control(const json & j) {
  if (!j.is_array() || j.size()!=2) {throw std::runtime_error("control requires two physical-N values");}
  Eigen::Vector2d u(j.at(0).get<double>(),j.at(1).get<double>());
  if (!u.allFinite()) {throw std::runtime_error("nonfinite control");}
  return u;
}

static json dump_state(const Vector6d & x) {
  if (!x.allFinite()) {throw std::runtime_error("production model output is nonfinite");}
  json j=json::array();
  for (int i=0;i<6;++i) {j.push_back(x(i));}
  return j;
}

static json evaluate(const json & request) {
  const std::string mode=request.at("mode").get<std::string>();
  json response={{"request_id",request.at("request_id")},{"mode",mode}};
  if (mode=="defaults") {response["params"]=dump_params(HydroParams{});return response;}
  const HydroParams p=parse_params(request.at("params"));
  const double dt=request.at("dt_s").get<double>();
  const int substeps=request.at("rk4_substeps").get<int>();
  if (!std::isfinite(dt) || dt<=0. || substeps<=0) {throw std::runtime_error("invalid integration configuration");}
  Vector6d x=parse_state(request.at("state_6"));
  response["received_params"]=dump_params(p);
  response["dt_s"]=dt; response["rk4_substeps"]=substeps;
  if (mode=="ode") {
    response["result"]=dump_state(USVDynamicModel::continuous_ode(x,parse_control(request.at("control_n")),p));
  } else if (mode=="step") {
    USVDynamicModel model(dt,substeps,p);
    response["result"]=dump_state(model.forward(x,parse_control(request.at("control_n"))));
  } else if (mode=="trajectory") {
    USVDynamicModel model(dt,substeps,p);
    response["states"]=json::array();response["states"].push_back(dump_state(x));
    for (const auto & u:request.at("controls_n")) {
      x=model.forward(x,parse_control(u));response["states"].push_back(dump_state(x));
    }
  } else {throw std::runtime_error("unknown mode");}
  return response;
}

int main() {
  std::string line;
  int errors=0;
  while (std::getline(std::cin,line)) {
    if (line.empty()) {continue;}
    try {std::cout<<evaluate(json::parse(line)).dump()<<'\n';}
    catch (const std::exception & error) {++errors;std::cout<<json({{"error",error.what()}}).dump()<<'\n';}
  }
  return errors ? 2 : 0;
}
