// Copyright 2026 USV Developer
//
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files (the "Software"), to deal
// in the Software without restriction, including without limitation the rights
// to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
// copies of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:
//
// The above copyright notice and this permission notice shall be included in
// all copies or substantial portions of the Software.
//
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
// IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
// THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
// OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
// THE SOFTWARE.


/**
 * @file mpc_node_main.cpp
 * @brief mpc_node 入口点。
 *
 * 对应 Python 版本: usv_mpc/mpc_node.py main()
 *
 * 用 MultiThreadedExecutor (3 线程) 让传感器回调与控制循环并发。
 */

#include <memory>

#include <rclcpp/rclcpp.hpp>
#include <rclcpp/executors/multi_threaded_executor.hpp>

#include "usv_mpc_cpp/mpc_node.hpp"

int main(int argc, char * argv[])
{
  rclcpp::init(argc, argv);
  // 构造期校验 (如 rc_override 要求 allowed_fcu_modes=[MANUAL]) 会抛异常。
  // 未捕获 = 进程 abort，systemd 记为 crash 且无可读退出码；这里转成干净的
  // 非零退出，让配置错误在日志里可区分于真正的运行时故障。
  std::shared_ptr<usv_mpc::MpcControllerNode> node;
  try {
    node = std::make_shared<usv_mpc::MpcControllerNode>();
  } catch (const std::exception & e) {
    fprintf(stderr, "[mpc_node] 启动配置被拒绝: %s\n", e.what());
    rclcpp::shutdown();
    return 1;
  }

  // SIGINT 时 rclcpp 信号处理器在 spin 返回前就触发 context shutdown;
  // on_shutdown 回调是发布安全停车指令的最后时机 (此刻 context 仍可用)。
  const bool research_logging = node->get_parameter("enable_research_logging").as_bool();
  auto stop = [ptr = node.get()]() {
      try {
        ptr->safe_shutdown();
      } catch (const std::exception & error) {
        fprintf(stderr, "safe_shutdown callback: %s\n", error.what());
      }
    };
  if (research_logging) {
    // Flush observations while the publisher context is still valid.
    node->get_node_base_interface()->get_context()->add_pre_shutdown_callback(stop);
  } else {
    node->get_node_base_interface()->get_context()->on_shutdown(stop);
  }

  rclcpp::executors::MultiThreadedExecutor executor(rclcpp::ExecutorOptions(), 3);
  executor.add_node(node);
  try {
    executor.spin();
  } catch (const std::exception & e) {
    fprintf(stderr, "[mpc_node] executor 异常: %s\n", e.what());
  }
  // 兜底: 非 SIGINT 退出 (异常等) 时 on_shutdown 未触发, 这里再发一次;
  // 若 shutdown 已进行过, publish 会抛错, 捕获即可 (幂等, 重复发送无害)。
  try {
    if (!research_logging || rclcpp::ok()) {node->safe_shutdown();}
  } catch (const std::exception & e) {
    fprintf(stderr, "[mpc_node] safe_shutdown: %s\n", e.what());
  }
  node.reset();
  if (rclcpp::ok()) {
    rclcpp::shutdown();
  }
  return 0;
}
