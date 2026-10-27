# C3.6 prepare_fixture 新 peer/close 路径只读复审

源 SHA、具体检查和限制见 [机器记录](/home/trevor/USV/.sgh-research/experiments/scheme_A_C3_6_adapter_20261013_12/review/driver_review_attempt01.json)。没有修改源码或运行fixture。此driver diff范围没有剩余P1/P2；Node里的时间/资源/tail问题独立见node_review_attempt01，不能由driver审查覆盖。

Peer pin来源是已经通过真实spawn/process/owned-manifest认证的 publisher角色：其run/boot/PID/startticks/exe/bin/source-bundle/typed-parameter digest/GID由observer二次核验，startup producer/config与角色绑定。角色复用保留旧N10的原始bundle与binary身份，只有新observer使用新bundle。spawn前仍逐文件校验source和binary SHA。

Driver先create-only发布带当前身份和单调时间的close request；等待最多1s的observer SHA确认，仍受整体15s关闭界。request/observer ack/publisher still alive/session normal end/cleanup/endpoint absence分开记录。缺ack或身份不同计close_errors后继续有限清理，不能导致通过。

Publisher退出后的正常tail证据仍要求publisher session已normal_end并flush、observer完整1..last序列和逐路完整transport人口join；任何少尾包/未知callback来源都不能用组件closed替代。旧observer-first保持明确all-rejected scope。

固定runtime仍25s准备、4s measurement、60s总界、15s关闭、正常hooks=0。这是新的有界shadow集成recipe，尚不证明20s动态/mixed、execute、连续唯一owner、plant接收或B4/M0b/B5/M4。SHA/身份值与owned source构成注册的可信artifact链；匹配请求文件本身并不提供任意外部写者的认证。
