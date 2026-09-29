// dump_golden_trajectory.cpp
// 金标准轨迹导出：链接 usv_mpc_ws 的 usv_model_dynamic.cpp，
// 以确定性控制序列积分 N 步，输出 CSV 供 Python 侧对拍（M1 门禁）。
//
// 用法: dump_golden_trajectory [n_steps] [out.csv]
// CSV 首行 "# params k=v ..." 记录所用水动力参数（Python 侧据此构造同参模型，
// 规避 C++ 头文件默认值与 usv_params_sim.yaml 辨识更新值不一致的问题）。

#include <cstdio>
#include <cstring>
#include <string>

#include <Eigen/Dense>

#include "usv_mpc_cpp/usv_model_dynamic.hpp"

int main(int argc, char ** argv)
{
  int n_steps = 200;
  std::string out_path = "golden_trajectory.csv";
  if (argc > 1) {n_steps = std::atoi(argv[1]);}
  if (argc > 2) {out_path = argv[2];}

  usv_mpc::HydroParams p;  // 头文件默认值
  usv_mpc::USVDynamicModel model(0.2, 4, p);

  FILE * f = std::fopen(out_path.c_str(), "w");
  if (!f) {
    std::fprintf(stderr, "cannot open %s\n", out_path.c_str());
    return 1;
  }

  // 首行记录参数，Python 侧解析对齐
  std::fprintf(f, "# params");
  std::fprintf(f, " mass=%.17g", p.mass);
  std::fprintf(f, " Iz=%.17g", p.Iz);
  std::fprintf(f, " xg=%.17g", p.xg);
  std::fprintf(f, " d_thruster=%.17g", p.d_thruster);
  std::fprintf(f, " Xu_dot=%.17g", p.Xu_dot);
  std::fprintf(f, " Yv_dot=%.17g", p.Yv_dot);
  std::fprintf(f, " Yr_dot=%.17g", p.Yr_dot);
  std::fprintf(f, " Nv_dot=%.17g", p.Nv_dot);
  std::fprintf(f, " Nr_dot=%.17g", p.Nr_dot);
  std::fprintf(f, " Xu=%.17g", p.Xu);
  std::fprintf(f, " Yv=%.17g", p.Yv);
  std::fprintf(f, " Yr=%.17g", p.Yr);
  std::fprintf(f, " Nv=%.17g", p.Nv);
  std::fprintf(f, " Nr=%.17g", p.Nr);
  std::fprintf(f, " Xuu=%.17g", p.Xuu);
  std::fprintf(f, " Yvv=%.17g", p.Yvv);
  std::fprintf(f, " Yrr=%.17g", p.Yrr);
  std::fprintf(f, " Nvv=%.17g", p.Nvv);
  std::fprintf(f, " Nrr=%.17g", p.Nrr);
  std::fprintf(f, "\n");

  std::fprintf(f, "step,x,y,psi,u,v,r\n");

  // 非零初值：含航向偏移与横漂速度，覆盖运动学旋转通道
  usv_mpc::Vector6d state;
  state << 0.0, 0.0, 0.5, 0.3, 0.05, 0.1;

  // 确定性控制序列：直航 / 差动右转 / 差动左转带倒车 / 零控 / 强差动
  auto control_at = [](int k) {
    Eigen::Vector2d u;
    const int phase = k % 40;
    if (phase < 10) {
      u << 10.0, 10.0;
    } else if (phase < 20) {
      u << 15.0, 5.0;
    } else if (phase < 30) {
      u << -5.0, 8.0;
    } else if (phase < 36) {
      u << 0.0, 0.0;
    } else {
      u << 22.0, -18.0;
    }
    return u;
  };

  for (int k = 0; k < n_steps; ++k) {
    std::fprintf(
      f, "%d,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g\n", k, state(0), state(1),
      state(2), state(3), state(4), state(5));
    state = model.forward(state, control_at(k));
  }
  std::fclose(f);
  std::printf("wrote %s (%d steps)\n", out_path.c_str(), n_steps);
  return 0;
}
