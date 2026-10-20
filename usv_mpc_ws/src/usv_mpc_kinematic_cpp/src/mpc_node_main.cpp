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
 * @brief mpc_node 入口点 (方案 A 运动学)。
 *
 * 对应 Python 版本: usv_mpc/mpc_node.py main()
 *
 * 用 MultiThreadedExecutor (3 线程) 让传感器回调与控制循环并发。
 * 与方案 B 的 mpc_node_main.cpp 结构一致。
 */

#include <memory>

#include <rclcpp/rclcpp.hpp>
#include <rclcpp/executors/multi_threaded_executor.hpp>

#include "usv_mpc_cpp/mpc_node.hpp"

int main(int argc, char * argv[])
{
  rclcpp::init(argc, argv);
  auto node = std::make_shared<usv_mpc::MpcControllerNode>();

  // SIGINT 时 rclcpp 信号处理器在 spin 返回前就触发 context shutdown;
  // on_shutdown 回调是发布安全停车指令的最后时机 (此刻 context 仍可用)。
  // 对齐 B: 信号线程上抛异常会逃逸进 shutdown 处理 → std::terminate, 必须捕获。
  node->get_node_base_interface()->get_context()->on_shutdown(
    [ptr = node.get()]() {
      try {
        ptr->safe_shutdown();
      } catch (const std::exception & e) {
        fprintf(stderr, "[mpc_node] on_shutdown safe_shutdown: %s\n", e.what());
      } catch (...) {
        fprintf(stderr, "[mpc_node] on_shutdown safe_shutdown: 未知异常\n");
      }
    });

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
    node->safe_shutdown();
  } catch (const std::exception & e) {
    fprintf(stderr, "[mpc_node] safe_shutdown: %s\n", e.what());
  }
  node.reset();
  if (rclcpp::ok()) {
    rclcpp::shutdown();
  }
  return 0;
}
