# P1 无输出校准运行器

仅在 Ubuntu 真正构建通过后由 root 部署和启动。此目录没有启动过 ROS、solver、Gazebo 或远端实验。脚本没有 execute 模式，也不把无输出校准结果升级为执行资格。

先 source /opt/ros/jazzy/setup.bash 和 /home/trevor/USV/usv_mpc_ws/install/setup.bash。使用系统 ROS Python，已有 experiment-root 目录，以及独立新 run-id：

```bash
python3 run_no_output_calibration.py \
  --contract /home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01/authored/p1_shadow_contract.json \
  --experiment-root /home/trevor/USV/.sgh-research/experiments/p1_execution_architecture_20261005_01 \
  --run-id p1_no_output_baseline_01 --duration 10 \
  --worker-sha256 ACTUAL_INSTALLED_WORKER_SHA256 \
  --regulator-sha256 ACTUAL_INSTALLED_REGULATOR_SHA256
```

两个预声明 SHA 参数可选；生产绑定优先显式传入 root 构建后的实际程序 SHA。无参数时运行器仍在启动前冻结当前文件 SHA，并将其与 /proc 中实际执行程序 SHA 比对，但这不替代 source/install manifest 门禁。

每个延迟采用独立 run-id，增加 --test-delay-ms 50、150、250 或400。默认10秒窗口不是20 Hz控制周期；synthetic /clock、odom 和 IMU 以50 Hz发布，path/profile 每秒重发同内容和固定配对戳。fixture 为零状态、静态零锚点，无实际 plant，不做跟踪性能比较。

受控 worker 路径阻塞增加 --test-native-block-ms 2000。这是调用 acados 前的 barrier，普通候选截止和 active watchdog 分开。当前 grace/TERM 期限下，2000ms barrier 可能在 KILL 前自行结束；不能据此声称 SIGKILL 路径被验收。若需要明确覆盖 KILL，应独立预声明更长 barrier，例如60000ms；仍仅诊断故障且需合同 fault_injection_enabled=true。不得复用同一 run 调整故障条件。

## 生命周期与证据

创建 run 目录和 run_context.json 后先检查已知 controller/Gazebo/fixture 进程、同 domain ROS 节点、输出话题 publisher。ROS_DOMAIN_ID=96、ROS_LOCALHOST_ONLY=1 对父 driver 和所有子进程一致。只发研究 stop 和 synthetic inputs，不创建 physical publisher。

MCAP recorder 先启动，等待 /clock recorder 订阅后再启动 worker；验证 acados/PID/boot/clock/N/dt/config/fault capability，再启动 no_output regulator 和 fixture。话题为合同四个 raw inputs、/clock、四个 /p1 消息和 /p1/stop，共10个。运行器不提前创建 raw_bag，rosbag CLI 独自创建。

停止首先发送 /p1/stop，给监管器合同 shutdown grace；保留 fixture/recorder 以收完整尾部。之后按监管器、worker、fixture、recorder 顺序有限关闭各自独立进程组。每次信号前核验 boot、leader start_ticks、PGID/SID，发现新的同会话子进程记录实际身份。没有 pkill、全局 PID 发现后杀进程、detach 或无期限 wait。所有 wait 窗口不超过60秒。任何 post-KILL 尚未退出、所有权不一致或身份未知，标 cleanup_failed；禁止新 spawn/自动重启，保留残留 PID 和失败原件。直接 child 由 nonblocking poll 回收；组内残留 zombie 也不被假报清理成功。

source 写入/flush、DDS/bag 和进程清理分别判断。worker/regulator source summary 原样收集，不把 RC0、KILL 后退出、supervisor cleanup_complete 或 recorder metadata 存在当作 source 完整证据。最终 runner_summary.json 的 normal_contract_complete、execute_qualified、source_completeness_proven、plant_acceptance_observed 均为false。root 的独立 checker 才做 source/bag 对账和故障机制验证。

交付：run_context.json、host_preflight.json、owned_process_ledger.jsonl、各进程 console、三个 source、raw_bag 和 runner_summary.json。任何失败保持原目录，不删除、不覆盖。同 run-id 再启动立即拒绝。

## 本地验证范围

test_owned_process_supervisor.py 是七个不启动任何进程的负例：PID复用、foreign session、排除无关进程组、post-KILL期限失败禁止再spawn、非有限等待拒绝、截断source尾部保留unknown，以及supervisor账本写入失败仍完成剩余cleanup并禁止新spawn。不依赖 ROS 或 Linux /proc 实际进程。它们不证明实际 POSIX 信号、native acados、ROS2 transport 或 MCAP 行为；这些必须在编译通过后由 root 做真实 Ubuntu 验证。
