# Pi5 部署指南 — USV NMPC 实机跑(acados + CasADi fallback)

本工作目录 `usv_mpc_ws_pi5` 专为树莓派5(aarch64, Ubuntu 24.04, ROS2 Jazzy)实机跑 NMPC(动力学,直接推力控制)而建,从开发机 `usv_mpc_ws` 精简而来:仅保留 NMPC,移除方案A/VRX/Gazebo 仿真。

## 求解器后端

`usv_mpc/mpc_dynamic.py` 的 `DynamicMPC` 优先用 **acados**(代码生成 SQP_RTI,亚毫秒级求解,专为嵌入式实时优化),失败时自动回退 **CasADi Opti+IPOPT**(`mpc_dynamic_legacy.py`)。

- acados 可用 → `backend=acados`,求解 <10ms。
- acados 不可用(未装/编译失败/codegen 失败)→ `backend=casadi_fallback`,求解 ~80-200ms(开发机 30ms,Pi5 ARM 慢 3-5 倍)。节点仍能跑,但可能逼近 200ms 预算。

mpc_node.py 调用接口完全不变,两个后端可热切换。

---

## 0. 系统准备

```bash
sudo apt update
sudo apt install -y build-essential cmake git python3-pip python3-dev swig \
  liblapack-dev libblas-dev
```

ROS2 Jazzy 按 https://docs.ros.org/en/jazzy/Installation/Ubuntu-Install-Debs.html 安装(若未装)。

## 1. acados C 库源码编译(无预编译 wheel,必须源码编译)

Pi5 是 Cortex-A76,aarch64。用对应 BLASFEO target:

```bash
cd ~
git clone https://github.com/acados/acados.git
cd acados
git submodule update --recursive --init   # 拉 BLASFEO/HPIPM 子模块

mkdir build && cd build
cmake .. \
  -DCMAKE_BUILD_TYPE=Release \
  -DBLASFEO_TARGET=ARMV8A_ARM_CORTEX_A76 \
  -DHPIPM_TARGET=GENERIC \
  -DACADOS_WITH_QPOASES=OFF \
  -DCMAKE_INSTALL_PREFIX=$HOME/acados_install \
  -DCMAKE_INSTALL_RPATH=$HOME/acados_install/lib
make -j4          # Pi5 4核;若 8GB 内存紧张用 -j3
make install
```

> 编译约 10-30 分钟。若 OOM,减小 `-j` 并关闭其它进程。

## 2. acados_template Python 接口 + CasADi

```bash
cd ~/acados
pip3 install -e interfaces/acados_template/    # acados Python 接口
pip3 install "casadi>=3.6"                      # acados 代码生成需要
```

## 3. 环境变量(写入 ~/.bashrc)

```bash
echo 'export ACADOS_SOURCE_DIR=$HOME/acados' >> ~/.bashrc
echo 'export LD_LIBRARY_PATH=$HOME/acados_install/lib:$LD_LIBRARY_PATH' >> ~/.bashrc
source ~/.bashrc
```

`ACADOS_SOURCE_DIR` 让 acados_template 找到模板和头文件;`LD_LIBRARY_PATH` 让运行时能加载 `libacados.so`/`libblasfeo.so`/`libhpipm.so`。

## 4. 验证 acados

```bash
python3 -c "from acados_template import AcadosOcpSolver; print('acados OK')"
```

输出 `acados OK` 即成功。若报错,检查第 3 步环境变量是否 source、第 1 步 `make install` 是否完成。

## 5. 部署工作目录

从开发机把 `usv_mpc_ws_pi5` 整个拷到 Pi5(如 scp/U盘):

```bash
# 在 Pi5 上
cd ~/usv_mpc_ws_pi5
pip3 install -r requirements.txt
rosdep install --from-paths src --ignore-src -y    # 装 ROS 依赖
colcon build --symlink-install
source install/setup.bash
```

## 6. 串口权限(MicoAir743 接 /dev/ttyAMA10)

```bash
sudo usermod -aG dialout $USER
# 重新登录或 newgrp dialout 生效
```

## 7. 首次启动(触发 acados 代码生成)

```bash
ros2 launch usv_bringup real.launch.py scheme:=B
```

首次启动时,mpc_node 构造 `DynamicMPC` 会触发 acados 代码生成(C 代码生成 + 编译 .so),约 **10-30 秒**,日志会提示。生成结果缓存到 `~/.cache/usv_mpc_acados/<签名>/`,**后续启动 <0.5 秒加载缓存**。

mpc_node 延迟 3 秒启动(等 MAVROS 连接),首次 codegen 期间 MAVROS 正在连接,基本无感。

确认 `/mpc/status` 话题:
- `backend` 字段应为 `acados`(成功)或 `casadi`(回退)。
- `solve_time_ms` 应 <50ms(acados)。
- 若 `backend=casadi`,检查第 1-4 步 acados 是否装好。

## 8. GCS IP 配置

默认 GCS IP `10.210.191.110` 是开发环境地址,Pi5 网络需改成本机实际 GCS IP:

```bash
# 方式一:启动参数覆盖
ros2 launch usv_bringup real.launch.py scheme:=B gcs_url:=udp://@<你的GCS_IP>:14550

# 方式二:改 src/usv_bringup/config/mavros_config.yaml 的 gcs_url 后重新 colcon build
```

---

## codegen 缓存说明

- 缓存目录:`~/.cache/usv_mpc_acados/<签名>/`(`usv_dyn_nmpc_lib.so`)
- 签名 = 结构参数 hash(nx, nu, N, 代价结构, 积分器配置, acados版本)。
- **改 usv_params.yaml(水动力学)或 mpc_params.yaml(Q/R/T_max 等)不需要重新 codegen**——这些是运行时参数(p_global / 约束边界),在 solve 时设置。
- 只有改 N、dt、模型结构(增减代价项/约束)才会改变签名,触发重新 codegen。
- 清缓存:`rm -rf ~/.cache/usv_mpc_acados/`

## acados 不可用时的回退

若 acados 编译/运行失败,节点自动用 CasADi+IPOPT:
- 日志会 WARNING 提示回退原因。
- 求解时间会上升(Pi5 上可能 150-300ms,接近或超 200ms 预算)。
- 超预算时 mpc_node 的失败计数器会触发 HOLD(零推力),需排查 acados 或调小 N。

## 预热缓存(可选,避免首次启动等 30s)

镜像预置或现场空闲时跑一次,提前生成 .so:

```bash
python3 -c "
import sys; sys.path.insert(0, 'src/usv_mpc')
from usv_mpc.mpc_dynamic import DynamicMPC
mp = {'mass':14.2,'Iz':2.13,'xg':0.12,'d_thruster':0.25,
      'Xu_dot':-2.0,'Yv_dot':-8.0,'Yr_dot':0.0,'Nv_dot':-0.363545,'Nr_dot':-1.621220,
      'Xu':-2.272063,'Yv':-2.629019,'Yr':0.0,'Nv':0.0,'Nr':-4.286144,
      'Xuu':-11.571784,'Yvv':-0.05,'Yrr':0.0,'Nvv':0.0,'Nrr':-0.001}
DynamicMPC(dt=0.2, N=20, Q_diag=(20,20,50,8,1,8), R_diag=(0.05,0.05),
           Rd_diag=(0.2,0.2), Qf_scale=8.0, T_max=25, T_min=-25, dT_max=80, model_params=mp)
print('codegen 完成,缓存已生成')
"
```

## 故障排查

| 现象 | 排查 |
|---|---|
| `backend=casadi_fallback` | acados 未装好;重做第 1-4 步,验证第 4 步 |
| `ImportError: acados_template` | 第 2 步 `pip install -e` 未做,或不在当前 Python 环境 |
| `libacados.so: cannot open` | 第 3 步 LD_LIBRARY_PATH 未设/未 source |
| 首次启动卡 30s+ | 正常 codegen;预热缓存见上 |
| 求解 `acados_status!=0` | 不可行;检查 T_max/dT_max/Q 是否合理,或参考 mpc_node 失败计数日志 |
| `/dev/ttyAMA10` 权限拒绝 | 第 6 步 dialout 组 |
| MAVROS 连不上 FCU | 检查 fcu_url(`/dev/ttyAMA10:921600`)、串口线、MicoAir743 串口配置 |

## 实跑前自检

1. `ros2 topic echo /mpc/status` —— 确认 `backend`、`solve_time_ms`、`success`。
2. `ros2 topic echo /mavros/state` —— 确认 FCU 连接、armed、mode。
3. `ros2 topic echo /path/reference` —— 确认规划器在发路径。
4. 确认外接 SSD 已挂载且可写:
   ```bash
   findmnt /mnt/usv_bags
   test -d /mnt/usv_bags && test -w /mnt/usv_bags && test -x /mnt/usv_bags
   df -h /mnt/usv_bags
   ```
5. 保持飞控未解锁,运行一次记录 dry run:
   ```bash
   ros2 launch usv_bringup real.launch.py record:=true
   ```
   约 30 秒后 Ctrl-C,等待 metadata 写入完成,再用 `ros2 bag info /mnt/usv_bags/usv_run_<时间戳>` 检查 odom、IMU、state 与 MPC 状态消息。
6. 手动模式下小油门测试推进器方向(T_L/T_R 正负对应)。
7. 切 AUTO/对应模式前,确认 MPC 在 ACTIVE 且无 HOLD。

完整录制、QoS 与回放说明见 [bag_recording.md](bag_recording.md)。
