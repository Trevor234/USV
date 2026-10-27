# 2026-10-07 资源合同与应用输送分账最小闭合：运行前反思

本包始于2026-10-06的只读审查；新部署/试验/验收使用2026-10-07。应用此前已使用的 control-preflight-reflect 与 control-postrun-retro；EDA route/STA/DRV/PPA指标在ROS任务中不适用，采用真实源码/类型/MCAP/owned进程及hash证据。

事实：现场1123保护资产无漂移、boot一致、controller/Gazebo与不可读cmdline均0。已装真实序列化最大合法Job=6460、Candidate=8204字节（4字节CDR encapsulation）；独立手算相符。两类型generated full_bounded=false，string序列化/反序列化没有声明上限检查，history发送有256检查，反序列化检查buffer并使用bounded容器。实际planner profile4dim，标签points/v_kappa_r_t/stamp_sec/stamp_nanosec。旧v14原失败和source/flush unknown不变。

根因排序：1. schema上限与应用处理域缺少绑定；2. resource JSON与固定实现兼容门缺失；3. 原source与bag计数不等于每条业务输送事件完整。假设：共享启动兼容门和额外复制前field检查能关闭合法编码应用处理边界；有限metadata拒绝保持原clear/任务失效语义；逐任务receipt/publish返回与独立ledger可发现未登记candidate、未解释missing/duplicate而不伪造DDS内部loss。

选择A：隔离复制上生产v28基础，新增revision5（数值控制/时序不改）、worker v9/regulator v13/resource header、配置与对象边界单测，新增有界source事件和独立application输送ledger；normal/delay150及必要metadata边界有限no_output验收。B（仅文档接受unknown）不能满足原计数要求；C（改raw subscriber/完整恶意字节穷举）超出当前最小域且无必要。

GO条件：前置现场hash/boot/host通过；新源码及两bin变动全部预声明、旧两bin备份；build与完整safety/runtime测试通过；资源边界实际序列化独立核对；新guard全量通过后才新run。

验收：资源数值真整型、合法边界/超限拒绝、reason UTF-8按字节、IDL外callback对象拒绝在额外复制/完整回显前；正常checker完整原门通过且真实native虚拟接纳；delay150原checker RC2/normal=false保持，机制/录制/source/lifecycle通过且0接纳；application ledger逐边exact multiset与全部registration，缺失/重复/内容不等/歧义使正常门false；DDS内部loss=null，不称已实测全局恶意资源安全或硬实时。

STOP：资产不明漂移、错误候选接纳、失效后新提交/激活、资源超限被正常处理、source/bag未解释缺口、未确认owned清理。保留原失败，不放宽旧截止/预算重判旧bag，不重复无新机制试验。execute_qualified=false；M0b/M4/F6/P1整体未完成，最新VRX仍v11。

只读inventory两次脚本参数/路径错误已独立保存，没有生产写入或ROS节点；修正后新事实文件成功，不能重判前两次为通过。
