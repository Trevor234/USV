# 第41批预检：当前普通receipt-lease即时stop

沿用control-preflight-reflect、control-theory-veto、control-postrun-retro；EDA route/STA/WNS/PPA不适用。

最新证据：39普通active与40当前gate+V1实际组合均通过；35旧lease验证使用900ms延后观察再恢复callback，不能顶替当前即时普通监督。普通策略支持active_watchdog/worker_capability_expired，44组件负例、两次seeded-auth真实Linux子进程及39实际active可按原域复用。

根因/差集排名与假设：
1. 调用顺序缺口：旧observe故意等待900ms，再观察/恢复，延后普通stop；假设pause实际ACK后立刻调用原supervise，能在真实600ms receipt lease终结前进入监控，并在原250ms通知/100ms认证到INT预算内派发。
2. 返回Worker退出与回调恢复边界不同：即时stop后Worker已退出，不能要求旧35“仍存活的合法身份消息”语义；假设恢复group后原pidfd guard拒绝排队消息且业务快照不变，不宣称获得完整旧payload CDR。
3. 记录与选定tick窗口：快速正常Worker退出可能短于一个200ms周期，不能凭空要求stop期间恰有一拍；假设整个真实lease pause/resume区间仍有至少2拍，原20ms jitter/240ms gap与无skip门限不变，实际stop窗口拍数如实报告。

A（选定）：只派生Python driver与lease_stimulus helper。沿用原完整准备/gate，先实际accepted Decision/Applied/认证phase健康前缀；提交受认证Worker callback pause、核对原3.5sTTL的实际ACK与无已见terminal；下一步直接调用原ordinary supervise。Source实际receipt lease过期后立即认证并派发owned stop；stop返回后才resume，观察至少一个旧Worker退出guard拒绝，随后沿用原Worker-terminal reception关闭与独立SQL/Stored核验。

B：修改普通监督内部或Observer gate/租约。没有新缺陷证据，扩大实现且丢失复用依据，不选。C：继续旧900ms观察后再监督，不能证明即时派发，不选。

GO：五个当前ELF和bundle不变，无C++构建、无新codegen。Worker none/0，Observer V1 none/V3 none、worker-gate、business_start gate原20s/2sTTL；DDS196/localhost/controlled C/synthetic nominal，Observer物理Writer=0。先旧资产全字节保护、入口组件、CLI、完整SDK loader、无所选遗留角色、源锁，再只运行ordinary_lease_01一次。45s总/15s关闭/128MiB，外55s INT+20s清理上限。旧hook0、150ms job/ready、T200ms、600ms receipt lease、1s active timeout、500ms worker grace+1s TERM+1s kill后检原值不变；500ms不是整个退出硬上限。

验收：门控前Decision/job0；首phase满足原150ms；健康前缀在pause前；monitor入口早于真实terminal；paired legacy因果和精确Worker身份/最后有效receipt/年龄严格>600ms；原Source FD/inode及manifest复认证→唯一dispatch→真实INT，通知≤250ms、认证到INT≤100ms；Worker暂停接收期间至少2次实际capability publish return且Worker进程未被SIGSTOP；五组清理、五返回0、Worker Source完整，无TERM/KILL实际需要；stop完成后resume，排队旧实例callback进程已退出拒绝，before=after且lease未续，无新submit/accepted；gate不自动timeout。原关闭ACK、live receiver尾接收、Stored/Fixture/API/全部SQL计数独立核验。14个当前raw深拷贝破坏检查均拒绝，原raw与所有源锁前后SHA不变。

失败停止重复，封存同次证据，不延长期限、不改原因、不用不同run拼接。当前选定普通lease通过仍不表示必要新身份恢复、B4八组或后续阶段取得资格。
