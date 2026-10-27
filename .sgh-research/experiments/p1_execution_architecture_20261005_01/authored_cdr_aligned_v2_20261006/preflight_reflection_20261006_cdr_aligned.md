# P1/M2 对齐原字节＋跨进程观察：新机制驱动最小计划

## 证据锁与纠正

原run p1_cdr_receive_20261006_01已经完整关闭，295 Python测试通过，但原 verification_cdr_v1 字节门失败，保留false。原MCAP直读与rosbag2两种读取格式一致：Job tail1483→1484、Candidate tail2899→2900，原prefix一致、末追加00；header3变header4，两empty无record。修改发生在进入MCAP前。原driver raw observer和sender在同一Python进程/participant，不能当作cross-process交付证明；不能把Candidate local失败/typed拒绝当成“相同长度的字节经过不同decoder结果不同”的确定结论。

依据 cdr_mcap_exact_readonly_audit_20261006.json / cdr_storage_readonly_audit_20261006.json / failed checker报告；1123保护资产无漂移。实际RTPS对齐或RMW缓冲责任仍是假设，不改生产RMW/接收层来掩盖差异。

## 根因排序 / A/B/C

1. flow_policy_mismatch：同participant raw观察不是跨进程观察，publisher原bytes不等于跨进程reader bytes。
2. model_mismatch：非4字节对齐mutation可能改变实际负载长度，tail-1不能可靠触发目标不可解析边界。
3. insufficient_evidence：空publish返回但无跨进程record，精确丢弃层unknown。

选择A：原生产源、bin、contract不变；增加owned独立PID raw observer，保存每条实际接收blob、长度hash与解码结果；driver raw仍负责原readiness。每类型before/header4/tail_minus4/after各1，共8尝试；有效CDR长度及mutation长度必须%4==0，删4字节而非删1。empty原尝试作为发送边界，不重复、不强求receiver通过。B修改middleware/生产raw订阅，C重复原不对齐矩阵，均NO-GO。

## GO和硬门

- 启动前后1123保护资产/host空闲/同boot；domain96 localhost/no_output；诊断参数原0；新工具目录create-only、所有文件hash固定。独立raw PID≠driver、owned身份和graph端点可追溯；无任何physicalpublisher。
- 8固定尝试各独立间隔约400ms；发送API返回、外部实际raw blob和actual MCAP bytes每topic/长度/hash各1；外部observer全量Counter必须与bag一致，末尾完整关闭。driver raw只作为另一观察，不能替代外部证据。
- header4/tail-4按实际解码与source观察分账，禁止假设绝不进callback；4前后foreign控制须进入既有业务身份门拒绝，注入ID不得native/接纳。注入前≥1且末次返回后新提交≥3真实native虚拟接纳；原生完整source/bag/输入/激活/lifecycle核验。
- 外部每条原blob保存，保存失败或decodeerror无记录→证据门失败；无真实executor ERROR不作为拒绝充分条件；目标reader具体drop继续unknown。本批只证明声明跨进程reader与record字节，以及实际业务恢复，不保证全部malformed或监管进程崩溃隔离。
- 原v28 normal回归本轮已过51/51/54，生产asset不变，新试验不再重复normal。只针对新增验证器做必要unit tests；已有295结果保持，本轮不同新tests另计。原v1失败不可重判。
- 实验有限10s观察，startup/owned cleanup原有有界门；出现controller/不可读identity即NO-GO，不停止不相关进程。节点崩溃/合法后缀不恢复/外部bag字节门失败则停止晋升；同门第2次失败且无新机制证据停止递归。

GO仅A。本次有明确新增机制证据，允许一次独立对齐验证；不允许fuzz、物理execute、全M2/P1/F6升级。M2仍需范围证据矩阵；M0b/M4/GP/plant等待办。EDA指标N/A，以ROS原blob/source/mcap/identity/hash为证据。
