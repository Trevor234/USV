# 方案 A 代码讲解 —— 白话版

> 写给：想看懂这套代码的人，不需要你是专家。
> 日期：2026-10-13
> 说明：这是技术文档的通俗版本，用日常语言解释代码在干什么、为什么这么写。

---

## 怎么用这份文档

- **如果你有控制基础**：直接跳到模块 3（实时性问题）
- **如果你要接手 P1 监管器**：先看模块 2 时间部分，再看模块 3 前半，然后直奔模块 7
- **如果你从零开始**：按顺序看，每讲末尾有练习题

**九个模块的逻辑**：

```
模块2: 时间怎么算  →  模块3: 程序太慢怎么办  →  模块7: P1 监管器（核心）
                                                      ↓
                                          模块8: 神经网络怎么上船
模块5: ROS2 的坑  →  模块6: 数据怎么存才可信  →  模块9: 怎么证明你没骗人
模块4: 多线程（可以穿插着看）
```

---

# 模块 2：时间 —— 为什么有三种时钟

**核心问题**：船上有三个"表"，用错了会出大事。

## 2.1 三种时钟，各管各的

想象你在厨房做菜：

| 时钟 | 像什么 | 用来干嘛 | 会不会跳 |
|---|---|---|---|
| **realtime（墙上挂钟）** | 家里墙上的钟 | 告诉你"现在几点" | **会**（手机联网校时会突然跳） |
| **monotonic（秒表）** | 厨房定时器 | 算"煮了多久" | **绝不跳**（按下去就一直走） |
| **sim time（游戏时钟）** | 游戏里的时间 | 算"船在仿真里过了多久" | **会暂停、会倒退** |

**第一条铁律：算时间差只能用 monotonic（秒表）**

比如你要算"这次控制花了多久"：
```cpp
开始 = 按下秒表
... 做控制 ...
结束 = 再看秒表
耗时 = 结束 - 开始  // ✓ 对的
```

如果用墙上挂钟算耗时：
```
开始看表 = 14:00:00
... 做控制期间，手机联网把时间往前调了 1 分钟 ...
结束看表 = 13:59:50
耗时 = ？？？  // 算出来是负数！
```

**第二条铁律：monotonic 秒表关机就归零，不能拿两次开机的读数做减法**

所以每条消息都要记一个 `boot_id`（开机编号），不同编号的时间不能比。

## 2.2 一条消息的"三个时刻"

船上的传感器数据（比如 GPS）从发出到用上，有三个时间点：

```
Gazebo 产生数据 ──网络传输──▶ 录像软件记录 ──▶ 我们的程序收到
   时刻①                      时刻②              时刻③
 (sim 时钟)                (录像机的钟)        (秒表)
```

| 时刻 | 叫什么 | 回答什么问题 |
|---|---|---|
| ① header.stamp | 发布时间 | 这条数据描述的是仿真世界里的"哪一秒" |
| ② bag 记录时间 | 录像时间 | 录像机什么时候看到这条数据飞过来 |
| ③ 收到时间 | 接收时间 | 我们的程序什么时候真正拿到它 |

**为什么要三个时刻？** 因为你要回答三个不同的问题：

- "这条 GPS 说的是船在仿真里哪个位置？" → 看时刻①
- "控制程序拿到数据时还新鲜吗？" → 看时刻③ 减去现在
- "事后看录像，这条推力命令和哪条 GPS 是配对的？" → 看时刻②（录像机同时看到的东西时间差小）

**大忌：不同时钟的时间绝对不能相减！**

```cpp
// ✗ 错的：sim 时间 减 秒表时间 = 没有意义的数字
耗时 = header.stamp - monotonic_now();  

// ✓ 对的：秒表 减 秒表
耗时 = monotonic_now() - 收到时刻;
```

## 2.3 时钟"坏了"的三种情况

仿真时钟（游戏时间）会出三种问题：

| 问题 | 意思 | 怎么办 |
|---|---|---|
| **reset（倒退）** | 时间突然往回跳（从 100 秒跳回 50 秒） | 纪元+1，之前的数据全作废 |
| **jump（大跳）** | 时间突然往前跳很多（跳了 10 秒） | 纪元+1，之前的数据全作废 |
| **paused（卡住）** | 时间不走了（一直停在 100 秒） | **不换纪元**，只是记录"暂停了" |

**"纪元"是什么？** 就像游戏的"第几局"——时钟出问题就算"新开一局"，新旧两局的时间不能混着用。

代码在这：[mpc_node.cpp:84-98](../src/usv_mpc_cpp/src/mpc_node.cpp#L84-L98)

## 2.4 怎么知道两条消息是配对的？

**问题**：录像里有推力命令、也有实际推力测量值，怎么知道哪条命令对应哪条测量？

它们**没有 ID**！没法直接对上号。只能靠"时间差"猜：

**规则**：录像机看到两条消息的时间差 < 20 毫秒 → 认为是一对。

```
录像时间轴：
0ms ──── 推力命令 A ──── 15ms ──── 测量值 X ──── 100ms ──── 推力命令 B
              ▲___________________▲  差 15ms < 20ms → 配对成功
```

**四条铁律**（代码在 [check_p0_contract.py:410-455](../../scripts/check_p0_contract.py#L410-455)）：

1. **时间窗口里只能有一个候选**：如果 20ms 窗口内有两个推力值相同的测量，没法判断对应哪个命令 → 拒绝
2. **配对过的不能再用**：测量值 X 配给了命令 A，就不能再配给命令 B
3. **先看时间、再看数值**：先用时间筛选候选，候选定了才比较数值对不对得上
4. **窗口外的数据保留但不做保证**：录像开始前/结束后的数据可能不完整，不强求配对

**为什么不能用 sim 时间配对？** 因为仿真跑得慢时（比如 0.5 倍速），同一个 sim 时刻可能对应录像里的好几秒——配乱了。

## 2.5 实时率（RTF）—— 仿真跑得够快吗

**RTF = 仿真时间流逝速度 / 真实时间流逝速度**

- RTF = 1.0：仿真 1 秒 = 现实 1 秒（刚刚好）
- RTF = 0.8：仿真 1 秒用了现实 1.25 秒（慢了，电脑带不动）
- RTF = 1.2：仿真 1 秒只用现实 0.83 秒（快了，电脑有余力）

代码在 [p1_clock_window.hpp](../src/usv_research_safety_cpp/p1_clock_window.hpp)（只有 45 行）

**怎么算**：看 400–600 毫秒的窗口内，sim 时间走了多少、秒表走了多少，一除。

**什么时候算不准**：窗口太短（<400ms）、时钟跳变、时钟暂停、纪元变了 → 都算不准。

**合格标准**：RTF 在 0.95–1.05 之间算正常，超出范围就拒绝。

## 小结

1. **算时间差只能用秒表（monotonic）**；墙钟会跳、仿真钟会暂停
2. **纪元 = 时间轴是否连续**：倒退/跳变换纪元，暂停不换
3. **配对规则**：先时间筛选、后数值比对，候选必须唯一、不能复用

## 练习题

**Q1：程序里有个 `clock_age_ns`，如果一直没收到 clock 消息就是 -1（负数），检查器要求它必须非负——为什么没崩？**

<details>
<summary>点击查看答案</summary>

因为有个"门禁"在前面挡着：启动录制数据之前，必须先收到 clock 消息，收到了才让你开始录（`capture_p0_runtime_context.py` 的检查）。所以正常流程走不到"clock 没到就开始录"的情况。

如果你绕过门禁硬要录，那就会踩到这个坑。
</details>

**Q2：两个地方都有"5 秒"的跳变阈值，是凑巧一样吗？**

<details>
<summary>点击查看答案</summary>

不是凑巧。两个地方都在判断"时间轴是不是断了"：
- `research_clock_`：决定要不要换纪元
- `ClockWindow`：决定 RTF 估计是不是作废了

它们判断的是同一件事（时间轴断裂），所以阈值一样是故意的。但注意：它们是两个独立的程序，如果将来只改一个，就会出现"一边认为时间断了、另一边认为没断"的矛盾。
</details>

**Q3：直行测试里，发布间隔最小是 130 毫秒（正常是 200 毫秒），最可能是什么情况？**

<details>
<summary>点击查看答案</summary>

仿真暂停后恢复的一次"追赶"。暂停时定时器还在触发（但被压着没执行），恢复后积压的那一拍赶紧执行了 → 间隔变短。

如果是时钟回退（reset），特征是时间戳往回跳 + 纪元加 1，不是间隔变短。
</details>

---

# 模块 3：实时性 —— 程序算太慢怎么办

**核心问题**：控制程序要 200 毫秒算一次，但有时候算不完。算不完的结果不能用，怎么办？

## 3.1 为什么迟到的答案不能用

船 0.8 米/秒，200 毫秒走 16 厘米。如果程序算了 400 毫秒才出结果：

```
时刻 0：  开始算，此时船在 A 点
时刻 200ms：本该发命令的时候 —— 但程序还在算
时刻 400ms：程序终于算完 —— 但船已经到了 B 点（离 A 点 32 厘米）
```

这个"算完的结果"是基于 A 点的船算出来的命令，现在船在 B 点，这命令**过期了**。

**更糟的情况**：如果你用了这个过期结果，下次算的时候还会基于这个错误的命令继续算 → 错上加错。

## 3.2 旧代码出过的事故

2026-10-03 审计时发现的问题（四连击）：

```
① 程序在一个线程里又算、又发命令 → 算的时候发不了命令
② 超时了只改个标志位"失败了" → 但没阻止后面用这个失败的结果
③ 连续失败 5 次以内，还是会把过期结果发出去 → 实测录像里有迟到命令 [22,-18]N
④ 更糟：过期结果还被当"下次的起点"存起来了 → 污染了后面所有的计算
⑤ 失败 5 次才发零推力 → 但零推力也不安全（船会漂）
```

**为什么"算完再加个 if 判断"修不好？**

因为只要"算"和"发命令"在一个线程里，算的时候就**没人能发命令**。这就是后面 P1 要把求解器拆到另一个进程的原因（模块 7）。

## 3.3 怎么判断"算超时了"

**需要两块表**：

| 表 | 量什么 | 用来判断什么 |
|---|---|---|
| **后端自报时间** | 纯计算花了多久（不算排队、不算被打断） | 算法本身慢不慢 |
| **墙钟时间（秒表）** | 真实世界过了多久 | 船等了多久 |

**判断超时只能看墙钟**，因为：
- 后端自报 50 毫秒，但如果程序被操作系统暂停了 200 毫秒，船已经等了 250 毫秒
- 后端不知道自己被暂停了

代码在 [mpc_node.cpp:828-831](../src/usv_mpc_cpp/src/mpc_node.cpp#L828-L831)：

```cpp
开始时刻 = 按下秒表
[调用求解器]
结束时刻 = 再看秒表
墙钟耗时 = 结束 - 开始  // 这个才是船等的时间
```

**判断规则**（[mpc_node.cpp:716-738](../src/usv_mpc_cpp/src/mpc_node.cpp#L716-L738)）：

1. **先看有没有坏数据**：时间是 NaN、负数、无穷大 → 直接拒绝（即使没开超时检查也拒绝）
2. **再看超没超时**：墙钟时间 **或** 后端自报时间任意一个超了 → 算超时

这叫 **fail-closed（安全门异常时当失败处理）**。

## 3.4 迟到后的"备用方案"

算超时了不能干等着，得有个备用方案：

| 方案 | 意思 | 代价 | 什么时候用 |
|---|---|---|---|
| **repeat-last** | 重复上次的命令 | 基于旧一拍的船位置 | 偶尔超时，首选 |
| **hold（保持 600ms）** | 一直发相同命令 | 误差累积，时间越长越大 | 短时间没新答案 |
| **ramp-zero（温柔刹车）** | 按 80N/秒的速度减到零 | 船会慢慢停，但是平滑的 | hold 时间到了 |
| **zero（直接零推力）** | 立刻切到零 | **推力突变，违反物理约束** | 最后没办法了 |

**为什么有个"80N/秒"的速度限制？**

船的推进器不能瞬间从 25N 跳到 -25N（物理上做不到，而且船会震）。80N/秒意味着：
- 从 20N 降到 0 需要 0.25 秒
- 从 25N 降到 -25N 需要 0.625 秒

代码里这个 80 叫 `rho`（希腊字母 ρ）。

**ramp-zero 的数学**（[p1_admission.hpp:131-136](../src/usv_research_safety_cpp/p1_admission.hpp#L131-136)）：

```
上次推力是 A，经过了 T 秒，现在最多能减掉 80×T
新推力 = max(0, |A| - 80×T)，符号和 A 一样
```

比如上次是 20N，过了 0.1 秒：
```
能减掉：80 × 0.1 = 8N
新推力：20 - 8 = 12N
```

再过 0.15 秒：
```
能再减：80 × 0.15 = 12N
新推力：12 - 12 = 0N（到底了）
```

## 3.5 "warmstart 污染" —— 为什么迟到的答案还要清缓存

MPC 求解器有个"热启动"机制：用上次的答案当这次的起点，算得快一点。

**问题**：如果上次的答案是**迟到的/错的**，用它当起点 → 这次也会算歪。

所以拒绝迟到答案时，**还要清掉这个缓存**：

```cpp
if (超时) {
    不发布结果;           // ① 迟到答案不用
    reset_warmstart();    // ② 清掉缓存，别污染下次
    恢复锚点();           // ③ 告诉求解器"上次实际发的是什么"
}
```

**"锚点"是什么？**

就是"上次实际发出去的命令是多少"。求解器需要知道这个，因为新命令不能和旧命令差太多（80N/秒的限制）。

**为什么有两个"上次的命令"？**

| 变量名 | 意思 | 用来干嘛 |
|---|---|---|
| `last_commanded_thrust_` | 程序准备发的命令 | repeat-last 时用（重复同样的准备过程） |
| `last_applied_thrust_` | 实际发出去的命令 | 恢复锚点时用（告诉求解器真实的起点） |

两个可能不一样，因为中间有个"映射"过程（比如乘个系数、限幅），所以要分开记。

## 3.6 看门狗 —— 怎么知道另一个程序卡死了

P1 系统里，求解器在另一个进程（程序）里。怎么知道它还活着、没卡死？

**两种检测**：

| 名字 | 检测什么 | 超时多久 | 意思 |
|---|---|---|---|
| **活跃任务看门狗** | 正在算的任务 | 1 秒 | "你说在算任务 X，1 秒还没算完 → 卡死了" |
| **能力租约** | 定期发"我还活着"的信号 | 600 毫秒 | "600 毫秒没收到信号 → 可能死了" |

**能力租约**只证明"最近收到过消息"，**不证明**：
- 消息是不是新鲜的（可能是网络延迟送到的旧消息）
- 求解器是不是在正常工作（可能活着但算不出来）

一旦判定"死了"，就是**终态**——不许自动恢复（因为可能是基于错误的判断恢复的）。

**三个时间的关系**：hold（600ms）≤ 租约（600ms）≤ 看门狗（1s）

意思是：**信任的时间不能超过检测的时间**。如果 hold 改成 2 秒，但看门狗只有 1 秒 → 程序卡死 1 秒才发现，但已经保持了过期命令 1 秒。

## 3.7 节拍调度 —— 跳过错过的拍子

每 200 毫秒一拍，像节拍器一样准时。但如果某一拍处理太久（260 毫秒），怎么办？

**不要"补拍"！** 补拍 = 执行一个更过期的计划。

应该：**直接跳到当前时刻该执行的拍子**。

```
计划：    100ms    200ms    300ms    400ms
          拍1      拍2      拍3      拍4
                    ↑
                  处理超时，醒来时已经 310ms
                    
错误做法：补拍2、补拍3，再做拍4 → 越补越乱
正确做法：跳过拍2/3，直接做拍4
```

代码在 [regulator.cpp:255-265](../src/usv_research_safety_cpp/regulator.cpp#L255-L265)

## 小结

1. **两块表**：后端量"计算多贵"、墙钟量"船等多久" → 判迟到只看墙钟
2. **拒绝迟到要连毒一起清**：答案不用、缓存重置、锚点恢复用实际发的值
3. **节拍和处理分开**：绝对时间睡眠、跳过错过的拍子、不补拍

## 练习题

**Q1：为什么 repeat-last 用 commanded、恢复锚点用 applied？**

<details>
<summary>点击查看答案</summary>

因为中间有个"映射"（比如乘系数、限幅）：

- **repeat-last**：重复"准备命令"的整个过程，包括映射 → 用 commanded（映射前的值）
- **恢复锚点**：告诉求解器"真正发出去的是多少" → 用 applied（映射后的值）

如果反过来用 applied 做 repeat，映射会被执行两次：
```
第一次：commanded(24) → 映射 → applied(12)  （假设乘 0.5）
第二次：repeat(12) → 映射 → 发出去(6)  ← 又乘了一次 0.5！
```
</details>

**Q2：锚点 unknown 时直接发 0，和"不能瞬间丢推力"矛盾吗？**

<details>
<summary>点击查看答案</summary>

不矛盾。完整的原则是："不能瞬间丢**已知的**大推力"。

如果锚点 unknown（不知道上次发了多少），从这个"编造的起点"做温柔衰减反而是错的（物理上不成立的衰减）。

此时直接发 0 是唯一诚实的选择 —— 不知道起点时，不要装作知道。
</details>

**Q3：hold 600ms、租约 600ms、看门狗 1s 为什么是这个顺序？**

<details>
<summary>点击查看答案</summary>

**信任的时间 ≤ 检测的时间**。

- hold = 盲目信任窗口（"我相信求解器还在算"）
- 租约/看门狗 = 检测窗口（"多久能发现它死了"）

如果 hold 改成 2 秒，但看门狗 1 秒：程序卡死 1 秒才被发现，但期间已经保持过期命令 1 秒了 → 检测来不及。

所以 hold 必须 ≤ 检测窗口，这样程序卡死时能及时发现。
</details>

---

# 模块 4：多线程 —— 怎么让程序不打架

**核心问题**：程序有好几个线程（同时做不同事情的"工人"），它们会同时碰同一份数据，搞乱怎么办？

## 4.1 多线程的三种"打架"

**打架 1：丢失更新（两个人同时改同一个数）**

```
变量 count = 0

线程A                    线程B
读到 count = 0
                        读到 count = 0
count + 1 = 1
写回 count = 1
                        count + 1 = 1
                        写回 count = 1

结果：count = 1（本该是 2！）
```

**打架 2：读到一半（一个人正在改，另一个人看到了改一半的数据）**

```
有个坐标 (x=10, y=20)

线程A 要改成 (30, 40)：     线程B 读坐标：
x = 30                      读到 x = 30
[还没来得及改 y]             读到 y = 20
                            得到 (30, 20) ← 这个坐标根本没存在过！
y = 40
```

**打架 3：TOCTOU（检查的时候 OK，用的时候已经变了）**

```
线程A：                       线程B：
if (路径不为空):              清空路径
    用路径做规划
    [刚判断完，还没用]
                             路径 = []
    [现在开始用路径]
    → 用了空路径！
```

这个最阴险，因为"检查"和"使用"中间有时间差。

## 4.2 C1 事故：一行注释里的海难预案

代码在旧版 kinematic 包 [mpc_node.cpp:479-481](../src/usv_mpc_kinematic_cpp/src/mpc_node.cpp#L479-L481)

**时序重现**：

```
控制线程：
    拿锁
    检查：路径有 300 个点 ✓
    放锁
    [准备做规划...]

路径回调（另一个线程）：
    清空路径（规划器发来空路径）

控制线程：
    拿锁
    用空路径做规划 → 得到一个"朝地图原点开"的答案
    放锁
    发布命令 → 船调头！
```

**为什么是海难？**

- 空路径是"正常消息"（规划器任务结束时会发），不报错
- "朝原点的最优解"数学上合法（没有目标时，离原点近算最优）
- 窗口很小（纳秒级），但每次任务结束都会打开

**修复（P1_ATOMIC_DYNAMIC_FREEZE_V1）**：把"检查→拷贝→构建规划"放在**同一个锁里**。

```cpp
拿锁
    检查路径 ✓
    拷贝路径
    拷贝船位置（6 个数）
    拷贝所有要用的数据
放锁

[用拷贝出来的数据做规划] ← 慢操作在锁外
```

**核心思想**："冻结"一个瞬间的世界，用这个冻结的快照做规划。

## 4.3 锁的顺序 —— 两把锁怎么拿

程序里有两把锁：

| 锁 | 保护什么 |
|---|---|
| `state_lock_` | 船的位置、速度等状态 |
| `control_output_mutex_` | 发布命令的出口 |

**死锁问题**：

```
线程A：                线程B：
拿 锁1                 拿 锁2
[想拿 锁2...]          [想拿 锁1...]
  等 B 放锁2             等 A 放锁1
    永远等...              永远等...
```

**解决方法：规定一个"拿锁顺序"**

本项目规定：先拿 `output` 锁，再拿 `state` 锁。

但有个地方故意"打破规则"：控制线程已经拿着 `state` 锁，要进 standby 模式时：

```cpp
// 控制线程手里拿着 state 锁
放掉 state 锁;              // ← 先主动放掉
enter_standby_();           // 这里面会拿 output 锁（再拿 state 锁）
```

**为什么要这样**：`enter_standby_` 里面会拿 output → state 的顺序，如果外面还握着 state 锁，顺序就反了。

## 4.4 关机的"原子性"

按 Ctrl-C 关闭程序时，控制线程可能正在算（几百毫秒的计算），怎么保证：

1. 立刻发一个"零推力"
2. 不让算完的过期结果再发出来

**代码**（[mpc_node.cpp](../src/usv_mpc_cpp/src/mpc_node.cpp) 的 safe_shutdown）：

```cpp
shutting_down_.store(true);      // ① 全局旗子：关机了！（所有线程立刻能看到）
拿 output 锁                      // ② 夺取发布权
发布零推力                         // ③ 立刻发
排空日志队列                       // ④ 把剩下的录像数据写完（可以慢，此时没别人和它抢）
```

控制线程有两道"岗哨"检查这个旗子：

```cpp
// 岗哨1：算之前
if (shutting_down_) return;

[开始算，可能算几百毫秒]

// 岗哨2：算完之后
if (shutting_down_) return;  // 别发过期结果
```

所以：按 Ctrl-C → 关机零推力先发 → 算完的过期结果被岗哨拦住。

## 4.5 有界队列：满了怎么办

研究日志用一个队列（排队的"管道"）把数据送到录像线程：

```
控制线程 ──▶ [队列，最多 1024 条] ──▶ 录像线程 ──▶ 写文件
  (快速塞入)                            (慢慢写)
```

**队列满了怎么办？**

**错误做法**：等空位 → 控制线程被卡住，船失控
**正确做法**：丢掉，但**记录"丢了几条"**

代码在 [research_logger.hpp](../src/usv_mpc_cpp/include/usv_mpc_cpp/research_logger.hpp)

**关键设计**（14 行的 enqueue）：

```cpp
msg.sequence = ++已生成数;    // ① 先分配序号
if (队列满了) {
    ++已丢弃数;               // ② 记录丢了
    return;                   // ③ 直接扔掉（不塞入队列）
}
队列.push(msg);
```

**为什么序号要先分配？**

因为录像里"缺号"就代表"丢了"：

```
录像里的序号：1, 2, 3, 5, 6, 7
                      ↑ 缺了 4 → 知道丢了一条
```

如果满了才分配序号，录像里就是连号的，看不出丢了。

## 4.6 进程身份证：PID 会被重复用

Linux 系统里，进程号（PID）是有限的（比如 1–32768），用完了会从头开始重复。

```
启动 worker 程序，PID = 1234
worker 崩溃
...过了一会...
系统启动另一个程序，也分配到 PID = 1234 ← 号码重复了！
```

如果只记 PID，没法区分是"原来那个 worker"还是"新程序碰巧同号"。

**解决方法：pidfd（进程文件描述符）**

代码在 [p1_worker_liveness.hpp](../src/usv_research_safety_cpp/p1_worker_liveness.hpp)（34 行）

```cpp
fd = pidfd_open(pid, 0);   // 向内核要一个"绑定这个进程"的句柄
```

**特性**：

- 这个 fd **绑定的是这个具体的进程**（不是号码）
- 进程死了，fd 上会有信号（POLLIN）
- 进程死后，即使 PID 被重复用，fd 还是指向"已死的那个"

**检查存活**：

```cpp
poll(fd, 0);  // 零超时：立刻返回，不等待
// 返回 POLLIN → 进程死了
// 返回 0 → 还活着
```

零超时的意思：不等、不阻塞、不发信号 → 放在决策关键路径上也没副作用。

## 4.7 测试怎么注入错误

**问题**：怎么测试"算到一半按 Ctrl-C"这种时序？

**方法**：用"条件变量"当"门栓"，卡住某个线程。

```cpp
// 测试代码
设一个门栓（关着）

开一个线程：
    开始算
    [算到一半被门栓卡住]
    
[主线程做点别的事，比如 shutdown]

放开门栓
等线程结束

检查：算完的结果有没有被发出去（不该发）
```

测试文件里有个 `friend class MpcControllerNodeTestAccess` —— 让测试能访问所有私有变量，但**生产代码里没有测试专用的 if**（不会因为测试代码污染正常代码）。

## 小结

1. **TOCTOU** 的解决：检查和使用放同一个锁里；慢操作在锁外
2. **队列满了诚实地丢**：序号先分配，录像里缺号 = 可观测的丢失
3. **跨进程/线程的身份**：PID 会重复用（用 pidfd）；生命周期靠所有权（join/SharedPtr）

## 练习题

**Q1：序号分配挪到锁外会怎样？**

<details>
<summary>点击查看答案</summary>

两个线程可能拿到相同的序号：

```
线程A：sequence = ++counter  （拿到 7）
线程B：sequence = ++counter  （也拿到 7！）
```

录像里会有两条 seq=7 的消息 → 检查器判定"录像损坏"，整个数据作废。

序号的唯一性是"缺号=丢失"判断的前提，必须和队列操作在同一个锁里。
</details>

**Q2：为什么 join（等线程结束）绝对不能在锁里？**

<details>
<summary>点击查看答案</summary>

工作线程退出前要拿锁（写 `++emitted`）：

```
主线程：              工作线程：
拿着锁                [想拿锁...]
join(等工作线程)       等主线程放锁
  [等...]              [等...]
    永远等...            永远等...
```

这叫"死锁"：两边互相等对方。

join 可能要等很久（几百毫秒排空队列），属于"慢操作"，必须在锁外。
</details>

**Q3：为什么用 poll 而不是 waitid？**

<details>
<summary>点击查看答案</summary>

`waitid` 是"收割者"调用（父进程等子进程死），即使加 WNOWAIT 标志，也会在内核里留下"有人在等"的记录。

而监管器的定位是"**观察者**"（只看、不管），不应该以"父进程"身份介入。

`poll` 是纯只读检查 —— 看一眼 fd 的状态，不留任何痕迹，不发信号，不收割。
</details>

---

---

# 模块 5：ROS2 工程 —— 那些容易踩的坑

**核心问题**：ROS2 有些机制不符合直觉，不小心就会掉坑里。

## 5.1 回调组 —— 控制"谁能和谁同时跑"

想象你雇了 3 个工人干活，有些活可以同时干，有些不行：

| 组类型 | 意思 | 像什么 |
|---|---|---|
| **Reentrant（可重入）** | 组里的活可以同时干 | 3 个工人可以同时刷 3 个不同的盘子 |
| **MutuallyExclusive（互斥）** | 组里的活必须排队 | 只有 1 个钥匙，拿到钥匙才能进厨房 |

**本项目的布局**（代码在 [mpc_node.cpp:447-452](../src/usv_mpc_cpp/src/mpc_node.cpp#L447-L452)）：

```
3 个工人（线程）

组1：传感器数据（GPS、IMU 等） ──▶ Reentrant（可以同时处理）
  - 为什么：5 个传感器互不影响，同时处理更快
  - 好处：控制卡住时，传感器数据还在收

组2：控制定时器 ──▶ MutuallyExclusive（必须排队）
  - 为什么：求解器（acados）不是线程安全的
  - 意思：上一拍没算完，下一拍不能开始算
  - 这不是风格问题，是硬约束！

组3：时钟消息 ──▶ MutuallyExclusive
  - 为什么：时钟观测要按顺序处理
```

**关键一句话**：求解器 capsule 必须单线程占有 → 控制组必须互斥。如果改成 Reentrant，两拍会并发进求解器 → 程序崩溃（未定义行为）。

## 5.2 QoS —— 为什么有数据却收不到

**QoS = Quality of Service（服务质量）**，决定消息怎么传输。

### 两种模式

| 模式 | 意思 | 适合什么 |
|---|---|---|
| **Reliable（可靠）** | 没收到会重发，保证到达 | 重要指令（必须收到） |
| **BestEffort（尽力而为）** | 发了就不管，丢了拉倒 | 高频传感器数据（丢一两条无所谓） |

### 阴险的规则

```
发布端 Reliable + 订阅端 BestEffort → ✓ 能收到（降级为 BestEffort）
发布端 BestEffort + 订阅端 Reliable → ✗ 完全收不到！而且不报错！
```

**真实事故**（2024-10-09 RTK 断流）：

```
MAVROS 发 GPS 数据 ──▶ BestEffort
                      ↓
ntrip_client 订阅 ──▶ Reliable（想要可靠）
                      ↓
                    不兼容！零消息！
```

结果：差分数据上不去 → RTK 失效 → 定位漂移。

更阴险的是：修好了账号（HTTP 401）之后还是没数据，因为第二个问题（QoS 不匹配）被第一个问题掩盖了。

**解决方法**：中继节点（[fix_qos_relay.py](../src/usv_bringup/usv_bringup/fix_qos_relay.py)，38 行）

```
MAVROS (BestEffort) ──▶ 中继订阅端(BestEffort) 
                         中继发布端(Reliable) ──▶ ntrip_client (Reliable)
```

把"不兼容"拆成两段"兼容"。

**排障口诀**：节点都活着但没数据 → 先跑 `ros2 topic info --verbose` 看两端 QoS 配不配。

### transient_local 的用法

**transient_local** = "后来的订阅者能拿到最后一条历史消息"

```
时间轴：
0s: worker 发"我能算"
1s: worker 发"我能算"
2s: [监管器这时才启动]
2.1s: 监管器立刻收到"我能算"（1s 那条的副本）
```

不用这个的话，监管器要等下一条（3s）才知道 worker 活着。

代码在 [solver_worker.cpp:27](../src/usv_research_safety_cpp/solver_worker.cpp#L27)：`.reliable().transient_local()`

## 5.3 launch —— 为什么参数没生效

**launch 是两阶段的**：

```
阶段1（声明期）：构建"要做什么"的清单
   - LaunchConfiguration 只是个名字（"config_hash"）
   - 看不到真正的值

阶段2（执行期）：真正启动节点
   - OpaqueFunction 里才能拿到值
   - 这时候做校验
```

**常见坑**：

```python
# 错误示范
def generate_launch_description():
    config_hash = LaunchConfiguration("config_hash")
    if len(config_hash) != 64:  # ✗ 这里 config_hash 是个符号，不是字符串！
        raise ValueError(...)
    
# 正确示范
def check_config(context):
    hash_value = context.launch_configurations["config_hash"]
    if len(hash_value) != 64:  # ✓ 这里才是真正的值
        raise ValueError(...)

def generate_launch_description():
    return [
        OpaqueFunction(function=check_config),  # 在执行期调用
        ...
    ]
```

**入口校验四连**（[p0_contract_recording.launch.py](../src/usv_bringup/launch/p0_contract_recording.launch.py)）：

1. run_id 是不是安全的文件名（只能有字母数字和几个符号）
2. config_hash 是不是 64 位十六进制
3. **目录必须不存在**（创建即证据，模块 6 会讲）
4. 两个目录不能互相包含（/data/run1 包含 /data/run1/sub → 不行）

**在 launch 里拦截比程序里崩溃便宜一个数量级** —— 程序启动要几秒，launch 校验是瞬间的。

### 隐藏参数的坑

```python
# 在 include 里传参数
"controller_vehicle": "path/to/vehicle.yaml"

# 但没有 DeclareLaunchArgument
# 功能正常，但 ros2 launch --show-args 看不到这个参数！
```

**问题**：新人不知道有这个参数，以为只有那几个写在 `declare_launch_argument` 里的。

**原则**：launch 参数的"声明"是给人看的文档，虽然不声明也能用，但别人不知道。

## 5.4 关机流水线 —— 为什么要用 pre-shutdown

按 Ctrl-C 关程序时，ROS2 的流程：

```
SIGINT 信号
  ↓
pre-shutdown callbacks（节点还活着，还能 publish！）
  ↓
executor.spin() 返回
  ↓
main 继续往下跑
  ↓
context 销毁（这之后不能 publish 了）
```

**关键时机**：录像数据要在 pre-shutdown 里排空，因为：

- 队列里可能还有 1024 条数据没写
- 每条要 publish 到 bag
- 如果等到 context 死了再写 → publish 失败 → 数据标记为"不完整"

代码在 [mpc_node_main.cpp:53-58](../src/usv_mpc_cpp/src/mpc_node_main.cpp#L53-58)：

```cpp
node->add_pre_shutdown_callback([node]() {
    node->safe_shutdown();  // 这里面会排空队列、发完剩下的数据
});
```

如果用 `on_shutdown`（更晚的时机）：context 半死 → publish 报错 → `normal_end=false`。

**信号线程的异常必须吞掉**：

```cpp
try {
    safe_shutdown();
} catch (...) {
    // 必须 catch，不然整个程序 std::terminate（没有优雅关机）
}
```

## 5.5 进程编排 —— 谁先起、谁不能联动死

**p0 入口的启动顺序**（[launch 文件](../src/usv_bringup/launch/p0_contract_recording.launch.py)）：

```python
return [
    recorder,        # ① 先启动录像
    mpc_controller,  # ② 再启动控制器
]
```

**为什么这个顺序**：

- DDS 发现协议要几百毫秒 → 如果控制器先起，开头的数据会丢（录像机还没准备好）
- 控制器退出时，不要联动杀掉录像机 → 因为控制器关机时还要写日志，日志要进 bag

**关机顺序**（手动 8 步流程）：

```
1. Ctrl-C 控制器
2. 等它写完 summary（录像队列排空）
3. 检查 summary（是不是 normal_end）
4. 再 Ctrl-C 录像机（给它 15 秒刷盘时间）
```

这个"谁先起、谁留多久"本身就是实验方法学 —— 不是随便排的。

## 小结

1. **并发能力 = 组 × 线程数**；求解器单占决定控制组必须互斥
2. **QoS 不匹配静默零**；修不了发布端就中继拆两段
3. **launch 两阶段**：校验放 OpaqueFunction；进程编排（谁先起、留多久）是实验方法的一部分

## 练习题

**Q1：如果把控制组改成 Reentrant 会怎样？**

<details>
<summary>点击查看答案</summary>

上一拍还在算（solve 阻塞中），下一拍回调会并行进入。

虽然 `state_lock_` 会让状态冻结部分串行化，但：
- `mpc_` 同一个 capsule 被并发调用 → acados 不是线程安全的 → 真正的崩溃
- `research_cycle_` 等变量被两拍交叉写 → 数据乱

控制组互斥不是风格，是 capsule 单线程占有的硬约束。P1 把求解器拆到独立进程就是它的彻底版。
</details>

**Q2：中继发布端用 `create_publisher(topic, 10)` 的 QoS 是什么？如果 ntrip 改成 BestEffort 订阅，还工作吗？**

<details>
<summary>点击查看答案</summary>

`create_publisher(topic, 10)` 默认补全成：KeepLast(10) + **Reliable** + Volatile。

如果 ntrip 改成 BestEffort 订阅：**还能工作**（Reliable 发布向下兼容 BestEffort 订阅）。

但会白付重传的开销 —— 不过 1Hz 的数据上，重传开销几乎为零。

真正的风险：如果有人把中继的**订阅端**"优化"成 Reliable（觉得可靠更好），当场重演事故。这就是为什么注释要把两端 QoS 的理由写死。
</details>

**Q3：为什么录制目录和研究目录都必须"不存在"？**

<details>
<summary>点击查看答案</summary>

**创建即证据** —— 谁创建的目录，谁就在里面留下"我是谁、什么时候创建"的信息：

- 研究目录：ResearchLogger 构造时创建，session_summary 里记录 producer/时间窗
- 录制目录：recorder 创建，metadata 里记录录制器身份

如果允许传入已存在的目录：没人能回答"这是谁建的、里面的旧文件是什么"。

这就是 F1 基线"拒绝覆盖"纪律在目录层面的应用 —— 新产物只能以新目录诞生。

`/data/run1` 和 `/data/run1_backup` 可以并存，因为它们平级、各自创建者明确。
</details>

---

# 模块 6：数据契约 —— 为什么一条消息要记这么多东西

**核心问题**：录了一堆数据，事后想分析"那一刻到底发生了什么" —— 发现答不上来。

## 6.1 数据 ≠ 证据

**数据**：发生过的字节的堆
**证据**：能回答问题的字节的链

假设你有一份录像（bag）：状态、推力、日志都有。现在要回答 **"t=34.5秒时船为什么左满舵？"**

你会发现缺一串东西：

- 那时候用的状态是**哪条 GPS** 的？（如果 x 来自 100ms 前的、y 来自 50ms 前的 → 这个"状态"物理上从未存在过）
- 发出的命令到底几 N？（中间有映射、限幅，发出去的和计划的一样吗？）
- 左右两路都发成功了吗？（两个话题，可能左成功右失败）
- 这些消息属于同一次运行吗？（节点重启过，序号从 1 重来，和重启前的序号撞了）

**把数据变成证据需要三层**（缺一不可）：

```
① 消息本体   —— 字段设计（.msg 文件）：该记什么
② 生产纪律   —— 发布端承诺：怎么保证记的是真的
③ 验收合同   —— 检查器（checker）：怎么验证没骗人
```

**只有 ③ 存在时，①② 才叫"承诺"** —— 否则只是注释里的愿望。

而且检查器自己也要被检查（177 项测试专测"它会怎么被骗"）。

## 6.2 身份块 —— 每条消息的"户口本"

8 条研究消息（StateSnapshot、AppliedControl 等）都有同样的开头：

```
schema_version         # 消息格式版本号（"p0-contract-v1"）
run_id                 # 哪次实验
producer_instance_id   # 哪个节点实例（run_id + 出生时刻）
baseline_id            # 基于哪个冻结基线
config_hash            # 配置指纹（64 位十六进制）
sequence               # 本流内的递增序号
clock_epoch            # 时钟纪元（模块 2 讲过）
steady_clock_domain    # "boot_id:steady_clock"（绑定到哪次开机）
...
```

**每个字段回答一个问题，对应检查器的一类拒绝**：

| 字段 | 回答什么 | 没有它会怎样 |
|---|---|---|
| schema_version | 字段的意思是哪个版本的 | 新旧格式混了，字段含义漂移 |
| run_id | 属于哪次实验 | 两次实验的数据混在一起 |
| producer_instance_id | 哪个实例发的 | 节点重启后，新旧流的序号会撞 |
| baseline_id + config_hash | 代码和配置的身份 | "这是什么版本跑的"答不上 |
| sequence | 流内顺序 | 丢消息发现不了（缺号=丢） |
| clock_epoch | 时间轴连不连续 | 跨纪元数据被错误拼接 |
| steady_clock_domain | 属于哪次开机 | 跨重启的时间差分算错 |

**关键细节**：`producer_instance_id = run_id + ":" + 出生时刻`

为什么不用 PID？因为 PID 会被重复用（模块 4 讲过）。用出生时刻，即使重启序号重来，也能区分。

**身份不是自洽就行**：消息声称的身份还要和**外部独立采集的 run_context** 对上（防止"全部伪造但内部自洽"）。

代码在 [check_p0_contract.py:186-200](../../scripts/check_p0_contract.py#L186-L200)

## 6.3 StateSnapshot —— 怎么证明状态是"原子的"

**承诺**："六维状态（x, y, 航向, u, v, 角速度）完全来自同一条 GPS"

**为什么这是问题**：

旧代码里，GPS 回调写 x/y/航向，IMU 回调覆盖角速度 —— **两个回调来自不同时刻**。

拼出来的"状态"在物理上从未存在过 → 给求解器讲了个假故事。

### 生产端：一条消息抽六维

代码在 [mpc_node.cpp:100-133](../src/usv_mpc_cpp/src/mpc_node.cpp#L100-L133)

```cpp
// GPS 回调里
从同一条 msg 抽 x, y, 航向, u, v, r  // 不做任何跨源拼接
```

如果 IMU 覆盖了 r（为了更灵敏）：**不隐藏，打标签**

```
state_kind = "controller_mixed"  // 而不是 "odom_atomic"
```

混合是合法的工程现实，但**必须可识别** —— 下游可以区别对待（混合状态有额外的年龄/偏斜检查，模块 7 会讲）。

**无效样本的处理**：

```
NaN 状态 → 照发，但：
    valid = false
    quality_reason = "为什么无效"
    state_6 = [0, 0, 0, 0, 0, 0]  （有限占位，不是原始的 NaN）
```

**宁可一条诚实的无效记录，不要一个看起来正常的假数**。

### 验收端：独立重建比对

这是我最喜欢的一段 —— [check_p0_contract.py:344-365](../../scripts/check_p0_contract.py#L344-L365)：

```python
# snapshot 声称自己来自某条 GPS（带时间戳、frame）
→ 去原始 GPS 流里把那条找出来
→ 用完全独立的代码重建六维（航向公式独立再写一遍！）
→ 逐分量比对（1e-5 容差）
```

**三个细节**：

1. **查找键是 (时间戳, frame, child_frame) 三元组** —— 同时间戳可能有多条（DDS 重发），所以"与其中任一条吻合即可"

2. **重建用的航向公式和生产端独立写了一遍** —— 不是复用生产代码！如果生产端的公式有 bug，独立重建会立刻暴露差异。**验证代码复用被验证代码 = 没验证**

3. **"不再二次旋转"的注释** —— 钉的是早期一个真实 bug：有人在快照路径上把 body 速度又转了一次世界系。测试 `YawNinetyDegreesPreservesBodyTwistWithoutSecondRotation` 专测这个。

**这就是"原子性证明"的完整闭环**：

- 生产端：从一条消息原子构造
- 验收端：独立重建比对

两个独立的实现算出同一个结果，才叫证明。

## 6.4 五个永久 false —— "不能声称的能力"

[AppliedControl.msg](../src/usv_research_interfaces/msg/AppliedControl.msg) 尾部：

```
bool plant_acceptance_observed        # 发布成功 ≠ Gazebo 接受了
bool force_measured                   # 没有力传感器
bool execution_atomicity_proven       # 左右两话题的原子性无法证明
bool exact_execution_timing_available # Float64 没时间戳
bool gp_labels_ready                  # GP 训练标签合同未闭合
```

**设计思想**：每个"不能声称的能力"在数据结构里占一个显式位置，而不是散在文档的免责声明里。

**逐个拆解**：

| 字段 | 堵住的谎言 | 真相 |
|---|---|---|
| plant_acceptance_observed | "命令发了所以船执行了" | publish() 只证明本地 DDS 调用完成 —— Gazebo 收没收到、执行没执行，一概不知 |
| force_measured | "发的 N 就是实际的 N" | 没桨力传感器，N 是**计算值** —— 水动力损失、桨空转都不知道 |
| execution_atomicity_proven | "左右同时执行" | 两个话题两次调用，中间隔任意久 |
| exact_execution_timing_available | "精确知道何时执行" | Float64 无 header，只能用 20ms 窗近似配对 |
| gp_labels_ready | "这数据能直接训 GP" | 残差标签需要(执行时刻的精确状态, 实际推力) —— 前四个 false 让它不可能 |

**注意链式依赖**：前四个 false 共同导致第五个 —— 你不能从"发布者视角的数据"直接构造"物理残差标签"。

**检查器执法**（[check_p0_contract.py:372-374](../../scripts/check_p0_contract.py#L372-L374)）：

```python
for key in ("plant_acceptance_observed", "force_measured", ...):
    if p.get(key) is not False:
        # 不是"建议为 false"，是"必须为 false"
        issue("unsupported_physical_claim", ...)
```

任何人想把它改成 true 骗过检查 → 整份 bag 无效。

**更深的动机**（研究文档的话）：科研里，**过度声称比错误更严重** —— 错误的数字可以被推翻，模糊的声称会污染所有引用它的结论。

五个 false 把"发布端观测"和"物理执行"之间的鸿沟变成了数据结构里的硬边界。

## 6.5 AppliedControl —— 一次发布的完整解剖

完整字段（按组）：

```
──事件语义──
event_semantics = "publisher_command"  # 声明"我只是发布者视角"
cycle_sequence                         # 关联哪个控制拍
control_source                         # 命令从哪来（solver/repeat_last/hold_zero...）

──请求 vs 最终──
requested_n    # 求解器原始输出
final_n        # 映射+限幅后实际下发的
map_scale / lower_n / upper_n  # 映射参数全程记录

──两路各自的发布证据──
left_publish_success / right_publish_success
left_publish_start_steady_ns / right_...
left_sim_time_ns / left_clock_epoch / right_...  # 捕捉两路之间的 clock 重置！

──前次锚点（下一拍变化率约束的起点）──
previous_anchor_known / previous_final_n

──五个永久 false + publish_error
```

**三个值得停的设计**：

### ① event_semantics 是自我限定

```
event_semantics = "publisher_command"
```

从命名上拒绝被解读为"物理执行事件" —— 三年后有人拿这数据写论文说"执行了 X"，翻出 schema，白纸黑字 "publisher_command"。

### ② 左右两路各自记 clock

为什么两路 publish 之间可能隔几毫秒，这期间 /clock 可能恰好回退（epoch+1）。

如果只记一份 clock：区间账本会用错误的时间轴拼"左发布 → 右发布 → 下一拍"。

各自记录后，检查器有 `channel_clock_epoch_mismatch` 拒绝码 —— 左右 epoch 不一致即联合区间无效。

### ③ 部分发布如实记录

左成功、右失败：

```
不是：抛异常吞掉、或发"综合成功"
而是：如实记 left=true, right=false，保留 publish_error 字符串
```

检查器判定：`partial_or_failed_publication` = 失败事件 —— **部分发布不是"降级的成功"，是"完整的失败"**（因为无法支持联合区间）。

测试 `RightPublisherExceptionRecordsActualPartialPublication` 用注入的右桨异常钉死这条语义。

## 6.6 负空间设计 —— "不该有的东西"

**正空间**：规定该有什么
**负空间**：规定不该有什么 —— **后者更能暴露 bug**

ReferencePrediction 的纪律（[check_reference_prediction.py:315-331](../../scripts/check_reference_prediction.py#L315-331)）：

```
规则1：prediction_available = false 时
      → 数组必须为空（不可用的预测不许带数组）

规则2：prediction_reason 必须与状态一致
      失败/迟到 → "solve_rejected"
      成功但预测缺失 → "prediction_missing_or_invalid"
```

生产端故意不复制失败解的 X/U：

```cpp
// 注释："Failed candidates are deliberately not copied"
if (失败) {
    不复制预测数组;  // 防"数据看起来丰富"
}
```

防什么：一个 NaN 混进去的数组，下游 `np.array(...)` 稍不注意就吃进去了。

空数组 + 明确 reason → **想用的人必须先看 reason**。

standby 拍同理：不 solve 的拍**不产生** reference 事件。检查器有 `reference_fabricated_for_no_solve` 拒绝码。

**负空间设计的价值**：契约不仅规定"该有什么"，还规定"不该有什么" —— 生成了不该有的 = 代码走了不该走的路径。

## 小结

1. **证据 = 数据 × 身份 × 独立验证** —— 复用被验证代码的验证不算验证
2. **能力边界写进数据结构** —— 五个永久 false 是"发布端观测 ≠ 物理执行"的硬围栏
3. **诚实优先于整洁** —— 部分发布算完整失败、无效样本照发但标记、失败解不带数组

## 练习题

**Q1：同时间戳有两条 GPS，snapshot 和其中一条吻合、另一条差 0.3m —— 检查器通过。合理吗？**

<details>
<summary>点击查看答案</summary>

**合理，且本系统必须如此**。

同 (时间戳, frame, child) 的两条，在本系统里几乎只能是 DDS 重投递（相同字节，重建结果逐位相同）。

0.3m 的差异意味着：上游给不同数据打了同一个时间戳 → 是更上游的失信。

**风险可接受的根基**：odom 是 VRX ground-truth（仿真真值，无 EKF 融合/重采样）。

如果换到实机 EKF 输出（同时间戳可能对应不同内部状态），这条容忍要收紧为"全部吻合"。

**契约的严格度必须与数据源语义匹配** —— 不是越严越好。
</details>

**Q2：换成带 header 的消息，能让 execution_atomicity_proven 变 true 吗？**

<details>
<summary>点击查看答案</summary>

**不能**。

原子性要证明的是**消费侧**（Gazebo）的采样落在同一控制区间。

换 header 只解决发布侧的时间标注。

缺的环节：Gazebo 各自订阅两个话题 → 各自回调 → 各自写物理引擎 —— 两个物理 step 之间可能只消费了左桨没消费右桨，**这条消息无法观察**。

要补齐需要 Gazebo 侧的接收确认（plant ACK）—— 这正是 `plant_acceptance_observed` 的含义：**证明责任在执行端，发布端换什么消息类型都到不了那里**。
</details>

**Q3：同 boot、同 run 但节点重启，区间怎么断开？**

<details>
<summary>点击查看答案</summary>

**序号连续性**断它。

重启后 sequence 从 1 重来：`..., 302, 303` → 重启 → `1, 2, 3, ...`

区间检查要求 `following.sequence == event.sequence + 1`：303 的下一个应该是 304，但实际是 1 → 不连续 → 断开。

两段数据各自内部序号连续、身份完备 → 各自能形成合法区间（直到各自的 end_unknown）。

**序号连续性的本质**："同一生产者不间断在线"的具体证明 —— 断档的唯一原因是死亡/重启/丢消息，三种都让"相邻事件间的物理保持"失去意义。
</details>

---

# 模块 7：P1 监管器 —— 怎么让求解器和发命令分开

**核心问题**：B 节点算命令和发命令在一个线程里 → 算的时候发不了命令。P1 怎么解决？

## 7.1 架构：两个进程

```
p1_regulator（监管器进程）                  p1_solver_worker（求解器进程）
  - tick 线程：每 200ms 决策一次              - 独占一个 acados capsule
  - prepare 线程：准备任务                   - 单工作线程
  - Sink 线程：写日志                        - 算错了就不再重启（隔离）
    │                                         │
    └──发任务──▶ /p1/solve_job ──────────▶   │
    ◀──收答案─── /p1/solve_candidate ◀───────┘
    ◀──心跳───── /p1/worker_capability（200ms 一次）
```

**进程边界的三个好处**：

1. **求解器卡住不会传染** —— worker 卡死在计算里，regulator 照常 200ms 一拍决策（用备份）
2. **故障隔离** —— worker 崩溃是进程死亡（pidfd 能看到），不是线程异常把整个程序带崩
3. **capsule 单占强制保证** —— 跨进程没有共享内存，独占是物理保证不是纪律

**唯一决策者原则**：regulator 的 tick 线程是全系统**唯一**能发命令的线程 → 每条命令都能追溯到"哪一拍、哪个时刻、哪次判断"。

## 7.2 固定 tick：发布不等求解

**时间轴**：

```
t_k（拍 k）          t_k + 150ms            t_(k+1)（拍 k+1）
  │                    │                      │
发布 q_k              候选提交截止            发布 q_(k+1)
  │                                            │
  └─ q_k 是上一周期就验证好的               └─ 快速核对激活条件再发
```

**关键洞察**：t_k 时刻发的命令（q_k）是**上周期就准备好的** → 发布动作本身不等任何求解。

求解慢只影响"下一拍有没有新候选"，不影响"这一拍有没有命令"。

**为什么不能提前发？**

150ms 算完了，为什么要等到 200ms 才发？

因为离散模型假设每个命令**恰好保持 0.2 秒**。如果 150ms 就发，第一段保持区间其实是 250ms（到下拍还有 250ms） → 模型的预测从此错位。

**命令时刻的精确性优先于提早**。

## 7.3 三个"时刻"：ready → committed → taken

一个候选从"算完"到"被执行"要过三道门：

```
worker 算完 ──发消息──▶ regulator 收到 ──▶ register_ready（点1: ready）
                                              "我有一个候选，目标是下一拍"
                     [时间流逝...]
                              
tick 线程（拍 k 循环尾部，睡过 150ms 之后）──▶ cutoff（点2: committed）
                                              "过截止了，就定这个"
                     [又过了 50ms...]
                              
tick 线程（拍 k+1 循环头部，到 200ms 了）──▶ take（点3: taken）
                                              "到点了，用它决策发布"
```

**为什么要三个点？**

| 点 | 线程 | 时刻 | 如果只有这个点 |
|---|---|---|---|
| ready | 回调线程 | 任意（≤150ms） | 回调和 tick 会抢锁、决策被打断 |
| committed | tick 尾部 | 150ms 后 | 定稿了但还没最后检查的窗口 |
| taken | tick 头部 | 200ms | —— |

**committed 和 taken 之间的 50ms** 是"定稿后、盖章前"的最后检查窗口 —— 这期间世界可能崩了（worker 死、输入变了），还来得及发现。

### Admission 类的关键规则

代码在 [p1_admission.hpp:103-130](../src/usv_research_safety_cpp/p1_admission.hpp#L103-L130)

**register_ready 的七道拒绝**：

1. `wrong_tick`：只接受"下一拍"的候选（防把旧拍的答案平移过来用）
2. `version_mismatch`：版本五元组必须一致（模块 6 讲过）
3. `time_contract`：deadline 必须**精确等于** origin+150ms（连这种等式关系都验证！）
4. `late`：注册本身不能晚于 deadline
5. `duplicate`：同一个 job 不能重复注册（64 深度去重窗口）
6. `cutoff_closed`：已经定稿的不能再改
7. `ready_slot_full`：就绪槽只有一个（一次只能候选一个）

**"closing at equality is forbidden"（边界不能关闭）**：

```cpp
// cutoff 的条件
if (!ready_ || now <= ready_->deadline) return false;  // 注意是 <=

// register 的条件
if (now > t.deadline) return "late";                   // 注意是 >
```

为什么 `now == deadline` 时 cutoff 不关、register 可以注册？

如果两边都用 `>=` 或 `>`，`now == deadline` 这一瞬间：
- cutoff 认为可以关了
- register 也认为可以注册

→ 谁先拿到锁谁赢，结果取决于调度 → **不确定**

现在的规则：`now == deadline` 时，**边界的所有权给注册方** → 语义唯一。

**take 的两个细节**：

```cpp
std::optional<Ticket> take(uint64_t target, int64_t now) {
    cutoff(now);  // ① 惰性补刀：取票时先执行到期的 cutoff
    ...
    if (committed_->target < target) {
        committed_.reset();  // ② 过期定稿作废
        return std::nullopt;
    }
    ...
}
```

① **防御性冗余**：即使循环尾部的 cutoff 没跑（比如调度延迟），取票时也补上
② **不补拍**：跳拍后旧定稿不能"补用"（它服务的时刻已经过去了）

## 7.4 四道墙：候选要闯的关卡

一个候选要活着走到"被执行"，必须过四道墙：

```
墙1：资格层（eligible）     "现在的世界适合做决策吗？"
墙2：候选层（candidate）    "这个候选本身可信吗？"
墙3：激活层（锁下决策）     "决策期间世界没变吗？"
墙4：提交层（commit 复查）  "最后一刻还成立吗？"
```

### 墙 1 精选（资格层）

检查的不是候选，是"此刻做任何决策的前提"。

代码在 [regulator.cpp:87-106](../src/usv_research_safety_cpp/regulator.cpp#L87-L106)

**混源双税**（`mixed_source_age_or_skew`）：

如果状态的角速度来自 IMU（而不是 GPS）：
- 年龄税：IMU 接收时刻距 now 不得超过 100ms
- 偏斜税：`|imu_时间戳 - odom_时间戳|` 不得超过 100ms

**为什么纯 GPS 不交税？** 因为六维来自同一条消息（原子的）。混源是用两条不同时刻的消息拼的 → 必须验证"它们描述的是接近的时刻"。

**两种"旧"（state_source_check）**：

```
            接收旧                 数据本身旧
            ↓                      ↓
        receive_stale          sim_lag
     (回调慢、DDS 拥塞)    (消息出生时就过期了)
```

为什么分开判？因为原因不同、修法不同：
- 接收旧 → 加 CPU、优化 DDS
- 数据旧 → 上游发布者的问题

**unknown_anchor**："不知道上一拍发了什么 → 新命令无法验证变化率约束"。

### 墙 2 精选（候选层）

检查"候选消息本身"可不可信。代码在 [regulator.cpp:210-222](../src/usv_research_safety_cpp/regulator.cpp#L210-222)

**foreign（身份六重验）**：

```
schema / run / boot / contract_hash / nominal_hash / worker_instance
六个字符串必须全等
```

防的是配置漂移：contract 换了一版但 worker 没重启 → 两边以为在同一个世界，实际参数分叉了。

**shape_or_time_contract（数值关系也是合同）**：

```cpp
if (j.horizon_steps != 20 ||
    j.deadline_steady_ns != j.tick_origin_steady_ns + 150000000 || ...) 
    return "shape_or_time_contract";
```

连"deadline 必须等于 origin+150ms"这种等式关系都验证 → 防止"prepare 代码算错预算"。

**job_echo_mismatch（候选必须完整回显任务）**：

候选里嵌着完整的 Job，regulator 把它和自己发出去的原件逐字段比对。

为什么？Job 里冻结了状态、参考、锚点 → worker 的解是基于这些算的。如果回显对不上 → "这个解基于什么算的"断了链。

**输入完整性靠输出回显证明**。

### 墙 3+4：检查做两遍

决策序分两段（代码在 [regulator.cpp:274-297](../src/usv_research_safety_cpp/regulator.cpp#L274-L297)）：

```
锁外（用快照 s）                锁下（用实时状态）
eligible(s, now)               eligible(实时状态, commit_now)
版本比对                       版本再比对
publication_history_check      publication_history_check（对实时锚点）
predict + state_check          command_check（对实时锚点和实时时刻）
...                            run_unusable_at_commit / tick_jitter ...
```

**为什么做两遍？**

因为"锁外检查"和"锁下发布"之间有时间差 → 这期间任意时刻，odom 回调可能更新了状态。

**锁下复查把"检查时刻"和"发布时刻"的距离压进锁的临界区** → TOCTOU 的终极解法（模块 4 讲过）。

**activation_input_changed_during_validation**：

```cpp
if (快照的 odom_seq != 实时的 odom_seq)
    reason = "activation_input_changed_during_validation";
```

用序号侦测变化（而不是逐值比对）→ 便宜且不漏（任何变化必然伴随序号+1）。

## 7.5 影子模式：零风险演习

**问题**：新系统第一次运行不能拿安全当赌注 → 怎么在真实环境里练习决策、但不碰船？

**答案：shadow 模式**

```
监管器全程运行完整决策逻辑（四道墙全走）
  └─ 但不发布任何物理命令 —— 船始终在 legacy B 手里
     └─ 决策流（接受/拒绝+原因码）照常记录进 bag
```

**逼真性靠"锚定"**：监管器的决策依赖"上一拍实际执行了什么"（锚点、变化率起点）→ shadow 下谁来告诉它？

**答案：订阅 B 节点的 AppliedControl** —— 五道门验证（代码在 [regulator.cpp:187-199](../src/usv_research_safety_cpp/regulator.cpp#L187-L199)）：

1. **baseline_id 必须是 F5 冻结基线** → 锚点来源必须是已知版本（数据合同按版本成立）
2. **map_scale 必须==1** → 无缩放直通
3. **生产者不许换人** → B 重启后 producer_instance_id 变了 → 锚点作废
4. **纪元一致** → 跨纪元数据不能用
5. **序号严格连续** → 断档即历史重置

**与 execute 的唯一差异**：

```cpp
if (mode_ == "execute") { 
    建 publisher;   // 只有 execute 有物理发布者
}
if (mode_ == "shadow") { 
    订阅 AppliedControl;  // 只有 shadow 订锚点
}

// 决策序、四道墙、fallback 全部共享
```

**同一套代码、零物理风险**。影子期的决策流证据**直接适用于** execute 期（不是"类似的"代码，是同一段）。

## 7.6 worker 纪律：quarantine（隔离）

代码在 [solver_worker.cpp:75-108](../src/usv_research_safety_cpp/solver_worker.cpp#L75-L108)

**单槽顶替**：一个 Pending 槽，新任务到来顶掉旧的（记 `pending_replaced` 事件）。

为什么不排队？因为任务是**时限商品** → 积压的任务到 deadline 全是废票。

**quarantine（隔离）**：

```cpp
if (!result.success || !result.prediction_available) {
    fatal_ = true;                    // 终态，本 run 永久
    terminal_numerical_ = true;
    event({{"policy", "quarantine_this_run_no_restart"}, ...});
    break;  // 退出工作循环，进程保持但不再接任务
}
```

**数值失败 → 本 run 永久退出，绝不重启**。为什么这么狠？

三个理由：
1. **失败有相关性** → 数值条件恶化（病态问题）重启后大概率再失败
2. **不可区分性** → worker 自己无法区分"输入偶然病态"和"我的求解器已损坏"
3. **pidfd 让死亡成信号** → regulator 立刻发现、标记 unusable、停止提交新任务

对照传统 crash→respawn：那是为了**可用性**（服务在线）；P1 要的是**可信性**（宁可没解，不要可疑的解）。

## 7.7 契约即代码：physical_execute_release_enabled

代码在 [p1_full_contract.hpp](../src/usv_research_safety_cpp/p1_full_contract.hpp)

**三层校验**（`load_contract`）：

```
读文件（≤64KB）→ SHA-256 与参数 hash 比对 → 解析 + 校验
任一步失败 → 进程起不来
```

校验什么：
1. **JSON 键不能重复** → 解析器默认"后者覆盖前者" → 前面的键是幻觉
2. **bool 不许冒充 int** → `true == 1` 在弱比较下成立，必须严格类型检查
3. **数值钉死** → 除了资源上限，N/dt/deadline/rho... 一个都不能改（改了就不是这个系统了）

**三档资格**（profile）：

| 档位 | 资格标志 | 允许的模式 |
|---|---|---|
| Diagnostic（当前） | `execute_qualified: false` | shadow / no_output |
| PreFreeze | 校准项冻结、仍 `execute_qualified: false` | no_output |
| Frozen | `execute_qualified: true` + 证据哈希 + 禁故障注入 | no_output / execute |

**最硬的墙**：

```cpp
inline constexpr bool physical_execute_release_enabled = false;  // ← constexpr

if (mode == "execute" && !physical_execute_release_enabled)
    throw std::runtime_error("physical execute release is disabled until B5/M4");
```

**编译期常量**，不是配置（改不了）、不是环境变量（设不了）。想开启必须**改源码重编译** → 二进制哈希变化被证据链看见。

**用摩擦力当安全机制** → 解锁条件从"改配置"（低成本、隐蔽）提升到"改代码重编译"（高成本、留痕）。

## 小结

1. **进程边界 = 最强隔离** → worker 独占 capsule、regulator 独占发布权
2. **固定 tick + 三线性化点** → t_k 发布上周期验证的 q_k；候选过三道门（ready → committed → taken）
3. **四道墙** → 资格（世界可用？）→ 候选（可信？）→ 激活（没变？）→ 提交（最后还成立？）
4. **影子模式逼真性靠锚定 legacy B**；quarantine 是可信性哲学（宁可没解不要可疑解）；execute 硬编码关闭是摩擦力机制

## 练习题

**Q1：legacy B 改了 `vrx_thrust_scale=0.9`，shadow 会怎样？**

<details>
<summary>点击查看答案</summary>

**安静退化** —— 改了 scale 的 B 发来的每条 AppliedControl 被门 1（map_scale!=1）**静默丢弃**。

→ 锚点永远 unknown
→ 每拍 `unknown_anchor` 拒绝
→ 全部 fallback（零/衰减）

监管器不崩溃、无配置级告警 —— 只会以"100% 拒绝"的姿态空转。

**对影子原则的意义**：影子不改物理系统 ✓，但**锚定契约（scale==1）是影子的隐性前提**，失效时无专门信号。

码分布诊断（`unknown_anchor` 占比）会让你去找原因，但不如启动日志一次声明便宜（review 建议加的就是这个）。
</details>

**Q2：quarantine 前候选已经 publish 了，为什么还要发出去？**

<details>
<summary>点击查看答案</summary>

虽然是"最后一条"，但它携带诊断价值：

- regulator 的墙 2（`solver_failed`）保证它不会被接受 → 只会作为带码记录进日志
- 候选里完整回显 Job + 后端耗时 + 失败原因 → **失败现场进 bag**

不发的话，regulator 只能看到"worker 忽然 silent"，现场丢失。

**失败也是证据，前提是如实标注**。
</details>

**Q3：从 Diagnostic 升到 Frozen 需要改 TickBarrier 的代码吗？**

<details>
<summary>点击查看答案</summary>

**不需要**。

`TickBarrier(ms, mode, fault_enabled)` 构造时：
```cpp
if (milliseconds && (mode != "no_output" || !fault_enabled))
    throw ...;
```

Diagnostic 档 `fault_injection_enabled: true` → 屏障在 no_output 下可用。

Frozen 档把契约字段改为 `fault_injection_enabled: false` → **任何非零屏障参数构造即抛异常**。

注入能力被数据自动关闭，无需删代码。

**代码保留可能性、契约决定可用性** → 危险能力的开关放在最难悄悄改的层。
</details>

---

# 模块 8：神经网络部署 —— ±1N 的船怎么来的

**核心问题**：训练好的神经网络怎么安全上船 —— 以及一个真实的单位错误事故。

## 8.1 PPO 部署基础

**训练 vs 推理**：

| 阶段 | 用什么 | 为什么 |
|---|---|---|
| 训练 | 随机策略：从 N(μ, σ) 采样 | 探索（走不同的路才能学） |
| 部署 | 确定性：直接用 μ | 可复现、可测试、可审计 |

**VecNormalize 陷阱**：

训练时观测先做标准化：`(obs - μ) / √(σ² + ε)` → 网络学的是"标准化空间"的映射。

**只导权重、忘了统计量（μ/σ²）→ 部署侧喂原始观测 → 输出垃圾**

而且这种垃圾不一定像垃圾（平滑函数给一堆看起来正常的数）→ 像"策略变笨了"。

**解法：折叠进图**（代码在 [export_policy.py:84-102](../../../usv_rl/usv_rl/export_policy.py#L84-L102)）

```python
class DeterministicActor(nn.Module):
    def __init__(...):
        self.register_buffer("obs_mean", ...)  # ← 统计量注册为 buffer
        self.register_buffer("obs_var", ...)

    def forward(self, obs):
        norm = (obs - self.obs_mean) / sqrt(self.obs_var + self.eps)  # ① 冻结的标准化
        norm = clamp(norm, -10, 10)                                    # ② clip
        mean = self.net(norm)                                          # ③ 网络
        return clamp(mean, -1, 1) * self.thrust_scale_n               # ④ 物理缩放
```

统计量进图 → **部署单元 = 单个文件**，不需要附属文件。

## 8.2 事故复盘：±1N 的船

**2026-10-03 审计发现** —— v5 ONNX 修复报告。

旧导出代码的输出端：

```python
# 从 [-1,1] 反缩放到 action_space
a01 = clamp(mean, -1, 1)
return act_low + (a01 + 1) * 0.5 * (act_high - act_low)
```

看起来无害 —— 但 v5 训练时把 action_space 改成了 **[-1, 1]**（之前是 [-25, 25]）。

代入：`act_low = -1, act_high = 1`

```
return -1 + (a01 + 1) * 0.5 * (1 - (-1))
     = -1 + (a01 + 1) * 0.5 * 2
     = -1 + (a01 + 1)
     = a01  ← 恒等变换！
```

**网络输出 [-1, 1] 直接发给了推力话题**（量程 ±25N）。

**后果**（VRX 实测）：
- 最大推力 ±1N
- 船 0.267 m/s 爬行（不是不动，是极慢）
- 看起来像"训练得差"，无任何报错指向单位

**四道防线为何全漏**：

1. **训练闭环自洽** → 环境 step() 接受 [-1,1] 自己乘 25
2. **导出验证用 actor 自己当 oracle** → 被验者=验证者，恒等 bug 双双通过
3. **部署侧无单位校验** → 拿到 [-1,1] 的输出，clip/限幅都"正常"工作
4. **人眼审查** → 数字在合法范围内（[-1,1] ⊂ [-25,25]）

**根因一句话**：单位是接口语义，而接口语义没有任何载体 —— 训练/导出/部署三方对"输出的物理含义"没有共同的、可机检的声明。

## 8.3 修复三件套

### ① 图内物理缩放

新 forward 第④行：`clamp(mean, -1, 1) * thrust_scale_n`

缩放**写进图里**，且 `--thrust-scale-n` 只接受 25.0：

```python
if scale != 25.0:
    raise ValueError("this v5 deployment contract requires thrust_scale_n=25.0")
```

为什么钉死 25 不允许任意值？因为 manifest、部署节点的 t_max、限幅全都假设 25 → 允许任意值等于允许三方再次错位。

### ② 独立 oracle 对拍

新的 `_verify`（代码在 [export_policy.py:123-141](../../../usv_rl/usv_rl/export_policy.py#L123-141)）

```python
"""Independent reference: saved VecNormalize API + SB3 deterministic predict.
Neither actor buffers nor its mapping function are used as the oracle."""
```

参考路径与被测路径**零共享实现**：

```
被测：ONNX 图（raw obs → 图内归一化 → clip → 网络 → clip×25）
参考：SB3 原生（raw obs → vn.normalize_obs() → model.predict(deterministic) → clip×25）
```

输入语料：64 条合成（固定种子）+ 可选真实观测 .npy。

容差：1e-3N（比推力分辨率小两个数量级）。

**验证的独立性高于覆盖率** → 验证自欺比不验证更危险（它给你继续错的信心）。

### ③ 契约式发布

产物 = onnx + manifest（成对）

manifest 关键字段：

```json
{
  "output_unit": "N",                  // ★ 单位声明（事故的核心缺口）
  "action_order": ["T_L", "T_R"],      // 左右语义
  "thrust_scale_n": 25.0,
  "physical_low_n": [-25, -25],
  "physical_high_n": [25, 25],
  "normalization_embedded": true,      // ★ 统计量在图内
  "onnx_sha256": "...",                // ★ 图的身份
  "source_model_sha256": "...",        // ★ 溯源
  "verification": {...},               // 对拍结果
  "export_command": "...",             // 可复现的命令
  "versions": {python/numpy/torch/...} // 环境指纹
}
```

三个层次：**声明**（单位/形状）、**溯源**（三个 SHA）、**证据**（对拍记录）。

发布协议（代码在 [export_policy.py:232-247](../../../usv_rl/usv_rl/export_policy.py#L232-247)）：

```python
临时文件 = mkstemp()
写图 → 校验 → 对拍 → 再哈希源文件
os.link(临时文件, 目标)           # ← 原子发布（目标不存在才成功）
os.link(临时manifest, manifest)
```

任何失败 → 撤销已发布的部分。**绝不覆盖既有产物**（`FileExistsError` 入口拦截）。

为什么？部署模型是证据链一环，覆盖后"上次部署的是什么"永远说不清。

## 8.4 部署侧硬校验

代码在 [rl_policy_node.py:54-90](../src/usv_rl_ros/usv_rl_ros/rl_policy_node.py#L54-L90)

四道检查：

1. **manifest 必须存在** → 裸 onnx 拒绝（旧产物不能上船）
2. **合同逐字段类型+值全等** → bool 冒充 int 也防
3. **双向锁** → manifest 说 25N ↔ 节点参数 t_max 也必须 25（两边谁单独改都失配）
4. **字节级 SHA256** → 文件被换/损坏/截断，哈希揭穿

加载失败的行为：

```python
self.model_contract_invalid = True  # 置终态标志
# 不崩溃、不退出 → 永远 STANDBY 零推力
```

为什么不自杀？对照 P1 worker 的 quarantine（自杀）：

- worker 死了有 regulator 接管
- **RL 节点死了，VRX 里推力会被 Gazebo 锁存** → 死节点留下的最后命令永续执行

**无人监管的节点，失败姿态是"活着且零输出"** → 自己就是自己的监管者。

## 8.5 NaN 纵深

NaN 的恶毒：`np.clip(NaN)` 返回 NaN → 一路进物理引擎爆炸。

**四道门**（代码在 [rl_policy_node.py](../src/usv_rl_ros/usv_rl_ros/rl_policy_node.py)）：

```
门1 _odom_cb:      四元数范数 + isfinite → 丢弃坏样本
门2 _control_step: self.state isfinite → nonfinite_state 零推力
门3 _control_step: 43 维观测 isfinite → nonfinite_obs 零推力
门4 _control_step: 推理输出 isfinite → nonfinite_action 零推力
```

为什么输出还要查？**干净输入也能算出脏输出**（float32 溢出/下溢）。

门 3 为什么必要？中间变换（如三角函数、插值）能自己造 Inf：

```
路径某 pose 纵坐标 Inf → np.hypot → s 含 Inf → np.interp → 观测含 Inf
```

**状态干净、观测脏** → 门 2 通过但门 3 拒绝。

**异常盾**（[:315-328](../src/usv_rl_ros/usv_rl_ros/rl_policy_node.py#L315-L328)）：

```python
def _control_loop(self):
    try:
        self._control_step()
    except Exception as exc:  # ← 捕获一切
        log.error(f"控制循环异常, 本拍零推力: {exc}")
        self._publish_thrust(np.zeros(2))
        # 定时器活着，下拍重试
```

为什么？Python 定时器回调异常会逃进 rclpy.spin → 节点死 → 推力锁存 = 失控船。

## 小结

1. **单位是接口语义，必须有数据载体** → manifest + 图内元数据双通道；部署侧不执法的合同只是文档
2. **验证的独立性高于覆盖** → oracle 零共享实现；验证自欺更危险
3. **无人监管的节点失败姿态：活着且零输出** → 有监管者（P1 worker）才自杀；无监管者（RL 节点）要苟活

## 练习题

**Q1：运行中替换 onnx 文件，算漏洞吗？**

<details>
<summary>点击查看答案</summary>

**不算** —— 威胁模型划对了。

加载时校验防**部署事故**（拿错文件/传输损坏/配错 manifest），发生在"导出机→部署机"链路。

运行中替换需要文件系统写权限 → 此时攻击者也能换节点代码本身，校验 onnx 无意义。

**每层防它那层的威胁，下层托底的上层不重复**。文件系统完整性由 OS/部署流程担保。
</details>

**Q2：门 3 必要的具体场景？**

<details>
<summary>点击查看答案</summary>

`_path_cb` 只查点数≥2，不查有限性。

场景：路径某 pose 纵坐标 Inf → `np.hypot(dx, Inf)` → s 数组含 Inf → `np.interp` → 观测含 Inf。

门 2（状态）通过，门 3（观测）拒绝。

**中间计算不是恒等映射，每道门检查的是它后面那个计算的输入**。
</details>

**Q3：训练侧加 assert 能更早暴露事故吗？**

<details>
<summary>点击查看答案</summary>

**不能**。

assert 验证的是"我这侧自洽"，而单位错位的定义是"每侧各自自洽、合起来错位"。

训练侧：输出是归一化值（[-1,1] 合法）
部署侧：输入是 N（[-1,1] 也合法，只是小）

**接口语义不存在于任何一侧，只存在于两侧之间** —— 只有"中间物"（manifest）能表达接口。

所以合同必须三方共持。
</details>

---

# 模块 9（终章）：验证方法学 —— 怎么证明你没骗人

**核心问题**：代码写了、数据录了 —— 怎么让别人（或三年后的自己）相信这些是真的？

## 9.1 基线冻结：Git 答不了的问题

**问题**："2026-10-05 13:47 那次 60 秒 pilot 运行的是什么代码？"

Git 能回答 HEAD 是什么，但：
- 工作区有 69 项未提交改动（dirty）
- install 目录是某次 build 的产物（可能与源码不同步）
- 训练模型是独立文件

**运行态 ≠ 任何 Git 对象** → 基线冻结补这块。

### collect 的五层档案

代码在 [collect_repair_baseline.py:283-378](../../scripts/collect_repair_baseline.py#L283-378)

```
① 身份：git head/branch/status/diff 全文
② 源码：白名单快照（146 项）—— 后缀过滤 + EXCLUDED 排凭据
③ 安装：实际 install 产物（177 项）—— prefix 必须指向本 workspace
④ 模型：5 项（onnx/manifest/checkpoint/vecnormalize）
⑤ 完整性：采集后重扫三组清单 + git 复核
```

**第 ⑤ 步是精髓**（[:369-378](../../scripts/collect_repair_baseline.py#L369-378)）：

```python
sources_after = 重新扫源码
if sources != sources_after:
    problems.append("source_changed_during_collection")
    # 采集中源文件变了 → 冻结失败
```

防的场景：快照进行时有人改了文件 → 快照是新旧混合体 → 哈希对不上任何真实时刻。

测试用**真实磁盘写入**注入变异（`after_copy` 缝）：

```python
def test_source_changes_during_capture_fail(self):
    path = self.root / "src/mpc_node.cpp"
    target, manifest = self.freeze(
        after_copy=lambda: path.write_text("mid collection mutation")
    )
    self.assertFalse(manifest["integrity"]["frozen_baseline_verified"])
```

### 真实基线长什么样

F5 的 [baseline_manifest.json](../.sgh-research/baselines/F5_20261005_atomic_freeze_01/baseline_manifest.json)：

```json
{
  "git": {"head": "1e5becae...", "branch": "codex/scheme-c-rl"},
  "dirty": true,  // ← 诚实记录：运行在未提交工作区上
  "source_count": 146,
  "installed_count": 177,
  "model_count": 5,
  "integrity": {
    "frozen_baseline_verified": true,
    "runtime_effective_verified": false,  // ← 静态冻结故意不声称运行时已验
    ...
  }
}
```

**`dirty: true` 不是缺陷，是诚实** → 同一 HEAD 不同 dirty 天然区分（Git 做不到）。

**`runtime_effective_verified: false`** → 静态身份 ≠ 动态身份（运行时参数由参数 dump + verify 另行建档）。

## 9.2 哈希链：锚定源头而非声明

```
p0_nominal_f3.yaml ──canonical 序列化──▶ nominal_effective.yaml
  (SHA: 78d7133f...)
      ↓
  p1_full_contract.hpp 的 "nominal_hash"
      ↓
  SolveJob.nominal_hash（每个任务回显）
      ↓
  SolveCandidate.job.nominal_hash（job_echo_mismatch 检查）
```

**验证方法 = 从源头重算**：

```bash
python3 -c "
import json, hashlib
nominal = json.load(open('p0_nominal_f3.yaml'))['/**']['ros__parameters']
doc = {'/**': {'ros__parameters': {'vehicle': ..., 'thruster': ...}}}
raw = (json.dumps(doc, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()
print(hashlib.sha256(raw).hexdigest())"

# 输出：78d7133fd4f11d47... ← 与 P1 契约里的 nominal_hash 逐字符一致 ✓
```

**不是"下游互相对账"**（那只证明下游一致）→ 而是**从源头独立重现**。

**递归伪造免疫**：C3.4 实验 —— 把 storage 里 120 条消息的 nominal_hash 全改假值，独立预像重算当场揭穿。

**攻击者能改所有声明，改不了哈希函数的数学**。

## 9.3 F1–F5：演进链作为证据

```
F1 三修复原样冻结（时间零点）
→ F2 数据契约
→ F3 四元数门禁 + 三实现对拍（291 例，差≤8.9e-16）
→ F4 nominal/plant 分离 + 单因素 probe
→ F5 原子冻结
```

**归因粒度决定结论强度**：

- 一个大提交：实验跑在上面 → "机制 X 有效"（但 X 和 Y、Z 混在一起）
- F4 单因素 probe：只改 plant.mass，其余哈希冻结 → "质量失配**单独**造成此差异"

**单变量保证不靠纪律（"记得没改别的"），靠哈希（别的变了冻结就失败）**。

`.pre_*` 备份 = **改前帧**（证明"从什么变成什么"），基线 = **改后帧** → 每步演进有前后两帧。

## 9.4 资格 vs 组件

C3.4 资格表：

```
组件：175+143+6+3 案例通过
阶段：strict_full_chain / B4/B5 / M0b / M4 / execute / dynamic20s / ... → 全部 false
```

**不矛盾，是两把尺子**：

- **组件**：给定版本/输入/前提下某链路验证过（砖）
- **资格**：全部必要条件满足才许进入后续动作（楼）

**组件数不累加成资格**。

175 项通过 ≠ 楼盖好 → 还差组装验证（strict 全链）、环境验证（B4/B5）、里程碑（M4 接管）...

**每项 false 是具体的待完成工作包，不是"还不太行"**。

代码层化身：`physical_execute_release_enabled = false` → **文档可以说服，代码不能**。

## 9.5 统计纪律：诚实边界的数学

### ① 零事故 ≠ 概率保证

```
n 次试验 0 次事故，单侧 95% 置信上界：1 - 0.05^(1/n)
n=100 → 2.95%
n=1000 → 0.3%
```

**直觉错误**："100 次没撞 → 97% 安全"

**正确读法**："事故率 > 2.95% 的系统有 95% 概率在 100 次里至少撞一次" → 100 次零事故只能排除"事故率高于 3%"的世界。

对 1% 的世界毫无分辨力。

### ② P99 达标 ≠ 硬实时

"端到端 P99 ≤ 150ms"是**筛选指标** → 说明 99% 的拍在预算内。

剩下 1% 呢？硬实时要求**最坏情况有界且被证明**（WCET 分析）。

### ③ 阈值先注册

所有阈值（幅值 1e-4N、动力学一致性 1e-4m、零容忍...）在**跑实验之前**写死。

防事后择优（p-hacking 工程版）："先看结果，再把容差调到刚好过"。

**数字改不动事实，只能改方法重跑**。

## 9.6 课程合流：九模块同一原则

```
模块2：时间域不混算 → 声称的耗时只在证据支持的域内成立
模块3：fail-closed → 无法验证的时刻按失败处理
模块4：诚实地丢 → 丢失可观测（缺号）优于完美伪造
模块5：崩溃是文档化行为 → 不满足前提就不带病运行
模块6：五个永久 false → 不能声称的能力占显式位置
模块7：资格与授权分离 → 数据说可以 ≠ 代码让你可以
模块8：独立 oracle → 验证与被验零共享实现
模块9：零事故≠概率保证 → 统计声称的数学边界
```

**这套体系防御的不是机器的失败，是人的自我欺骗** —— 从"这数据应该没问题"到"100 次没撞说明安全"到"就试一次真的执行"。

这个项目把"不被污染"做成了**机器强制的纪律**。

## 小结

1. **基线冻结回答 Git 答不了的问题**（"那次运行的是什么"）→ 采集中稳定性、dirty 如实记录、静态/动态身份分开声称
2. **哈希链锚定源头而非声明** → 从源头独立重算；递归伪造免疫
3. **组件 ≠ 资格，零事故 ≠ 安全** → 资格表列差什么、constexpr 拒绝提前解锁、统计声称按数学边界转述

## 结课三题（留白，待你未来作答）

1. **提交策略设计**：69 项未提交 vs 五层档案的讽刺 → 按什么边界切分提交？`.pre_*` 去哪？`.sgh-research/`（7GB）进不进 Git？
2. **`closed_publisher_interval` 的精确语义**：左右两路 publish 的起止 steady 时戳（②域、同进程）证明什么、不证明什么？
3. **GP 上线的实战检验**：`Version.model` 递增时 → version_mismatch / repeat-last / 重心化等价各自够不够？哪个证据链最薄弱？

---

# 知识地图

| 模块 | 你能做的 |
|---|---|
| 2 | 读任何研究消息的时序字段并说出证明边界 |
| 3 | 评审任何控制代码的迟到处理并指出缺哪层 |
| 4 | 审计多线程节点并写受控交错测试 |
| 5 | 排查"没数据"故障；设计进程编排 |
| 6 | 为任何机器人系统设计数据契约和验收器 |
| 7 | 读 P1 任何一行代码并说出它在哪堵墙 |
| 8 | 部署任何模型不再犯单位错误 |
| 9 | 把工程工作组织成可审计的研究证据 |

**贯穿始终的一课**：这个项目最独特的产出不是监管器本身，是它把"诚实"工程化的方式 —— 每个"不能声称"都有字段、每个拒绝都有名字、每个版本都有哈希、每个资格都有清单。

**机器不会撒谎，但人会说"差不多" —— 这套系统的全部精密，都在消灭"差不多"。**
