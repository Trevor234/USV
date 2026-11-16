# 现场声明模板（必须由在场操作者本人填写，工具不得代签）

写到 `<R>/evidence/operator-attestation.json`，内容精确为：

```json
{
  "operator": "<在场操作者姓名/工号>",
  "confirmed_at_utc": <CLOCK_REALTIME 纳秒整数>,
  "valid_until_utc": <CLOCK_REALTIME 纳秒整数>,
  "vessel_secured": true,
  "no_mission": true,
  "propulsion_power_isolated": true,
  "local_emergency_stop_available": true
}
```

四项必须全为 `true`，任一缺失或为 false，driver 与监督器都拒绝启动。
`valid_until_utc` 到期后运行中的接管会以 `commissioning_authorisation_expired`
有界关闭；不在运行中续签，延长窗口必须新开一次授权事务。

**为什么不能由工具填写**：`armed=false` 只是飞控软件状态，不等于推进器动力被
物理隔离。物理隔离、船体固定、无航行任务、可就地急停这四件事只能在现场确认。
