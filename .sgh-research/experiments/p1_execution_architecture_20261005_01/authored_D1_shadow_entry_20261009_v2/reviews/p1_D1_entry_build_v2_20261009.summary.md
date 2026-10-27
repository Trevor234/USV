# D1 entry v2 有限构建与针对验证

configure/compile/三target返回0，41case全run，23新+18继承，无disabled/skipped/failure/error；5个owned步骤完整清理，原3322与v1全部199文件无漂移，host前后无控制器/Gazebo。runtime SHA 94c505677b105e148ecec34769c92f6983feac8316877e0a6d32a9e737be7416。v1同源行GTest标签失败保留，v2只拆行；生产source相同。

仅验证隔离入口有限机制。新dynamic simulation=0，rclcpp source-linked测试进程实际运行；完整生产ready/graph、external worker argv、strict shadow driver/reader、当前域、时间参数及统一压力资格未闭合。D1动态No-Go、execute false。
