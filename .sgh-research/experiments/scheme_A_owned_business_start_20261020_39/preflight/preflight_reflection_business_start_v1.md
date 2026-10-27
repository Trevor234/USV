# 第39批预检与最小实施（2026-10-20）

沿用control-preflight-reflect、control-theory-veto和control-postrun-retro的证据与门限结构。EDA route/STA/WNS/PPA不适用。

最新事实：第38批三次失败原样冻结。第一轮release调用153ms、绑定317ms、首phase实际完成晚181.627ms，超150ms后没有job；第二轮Recorder等待缺少Observer Writer；第三轮提前参数查询不可用，具体构造/发现原因未证。反复换启动顺序的假设不足，普通策略未进入。旧资产、普通44组件与两个unit-auth真实Linux子进程、原性能NoGo分开引用。

排名：1）业务tick在全准备完成前已开始，Publisher释放和绑定昂贵时可拿到旧Decision；2）Recorder依赖所有声明topic，使提前就绪不成立；3）早参数服务可用性未证明。现有可成功准备的完整图/参数流程应保留。

A（选定）：派生Observer受认证单次业务启动gate。端点、Source、参数服务、Applied/Worker/传感器接收照常，tick/prepare暂不创建；driver完成原五角色认证、完整图、所有参数查询、Reader匹配、release后真实Publisher绑定和初始零Applied/LegacyReady，再发布新create-only请求。Observer绑定driver live PID-start/exe/argv与脚本SHA、run/boot/合同、双方manifest；原就绪、活性、源年龄、版本及零锚点在真正启动前重验。

B：Publisher预绑定。还需处理pre-release旧Decision/late pending，扩大该角色行为，本批不选。C：继续旧脚本换时机，不提供新机制，不选。

GO：实现、review与Native。只新Observer ELF，四角色沿用；合同150ms ready/200ms T/20ms jitter、旧五hook0和物理Writer0保持。默认immediate/空路径/0预算独立；新policy必须显式fault-enabled witnessed shadow、20s gate等待、2s请求TTL。门控不持业务锁等待文件/认证；未启动的取消、无请求、超时和Source失败都不能产生业务授权。启动后仍调用原tick_loop并使用其原1s lead与每job deadline。

构建180s、Native45s，初次加至多2次修复，各目录留证。Native源链接测试覆盖身份/类型/版本/重复/未知字段/时间/原前提/取消和实际callback可运行、无gate tick入口不发布；旧activation Native一起运行，有种入Ticket/RTF/lease/readiness的局部前提，不是全阶段资格。

Native、源锁、loader、CLI通过后，只另预注册一个当前版本实际确认。唯一目标是门控前完整端点/参数就绪与零业务，门控后正常首phase、健康job、真实active刺激及普通无SIGSTOP stop。Source/Witness/Stored/Fixture/API结果独立核验；不放宽150ms，不合成终结，不清空旧失败。真实lease普通路径、最终V1/组合与B4整体另按依赖决定，不自动继承。
