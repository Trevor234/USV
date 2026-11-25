// 组会汇报: 基于 PPO 的 USV 路径跟踪强化学习 (方案C) — 22 页
// 运行: cd report_assets && node build_ppt.js  (数据来源见各页 source 行, 不编造数字)
const pptxgen = require("pptxgenjs");

const p = new pptxgen();
p.layout = "LAYOUT_WIDE"; // 13.33 x 7.5
p.author = "trevor";
p.title = "基于 PPO 的无人艇路径跟踪控制 — 方案C 阶段汇报";

// ---- 设计系统 ----
const W = 13.33, H = 7.5, M = 0.5;
const BG = "FFFFFF", DARK = "0B2E33", PRIMARY = "0E5F52", TINT = "EAF2EF",
      ACCENT = "D95F02", TEXT = "1F2937", MUTED = "6B7280",
      ONDARK = "F1F5F4", ONDARK_MUT = "9FB8B2", BORDER = "C9D6D1";
const FONT = "微软雅黑";
const ASSETS = __dirname;
const OUT = __dirname + "/../组会汇报_方案C_RL路径跟踪_20261006.pptx";

const shadow = () => ({ type: "outer", color: "0B2E33", blur: 7, offset: 2, angle: 45, opacity: 0.18 });
const bu = () => ({ code: "25B8", indent: 12 });

let pageNo = 0;
function slide(dark) {
  const s = p.addSlide();
  s.background = { color: dark ? DARK : BG };
  pageNo++;
  if (pageNo > 1) s.addText(String(pageNo), { x: W - 0.9, y: H - 0.42, w: 0.5, h: 0.3, fontSize: 10, fontFace: FONT, color: dark ? ONDARK_MUT : MUTED, align: "right", margin: 0 });
  return s;
}
function header(s, section, title, sub) {
  s.addText(section, { x: W - 3.0, y: 0.32, w: 2.5, h: 0.3, fontSize: 12, fontFace: FONT, color: MUTED, align: "right", margin: 0 });
  s.addText(title, { x: M, y: 0.3, w: 9.6, h: 0.62, fontSize: 27, fontFace: FONT, bold: true, color: TEXT, margin: 0 });
  if (sub) s.addText(sub, { x: M, y: 0.94, w: 11.0, h: 0.34, fontSize: 14, fontFace: FONT, color: MUTED, margin: 0 });
}
function card(s, x, y, w, h, fill) {
  s.addShape(p.shapes.ROUNDED_RECTANGLE, { x, y, w, h, fill: { color: fill || TINT }, rectRadius: 0.07, line: { color: BORDER, width: 0.75 }, shadow: shadow() });
}
function srcLine(s, text, y) {
  s.addText("来源: " + text, { x: M, y: y || H - 0.46, w: 11.0, h: 0.3, fontSize: 10.5, fontFace: FONT, color: MUTED, margin: 0 });
}

// ============ S1 封面 (dark) ============
(() => {
  const s = slide(true);
  s.addImage({ path: "/home/trevor/USV/vrx_ws/src/images/sydney_regatta_gzsim.png", x: 8.1, y: 0, w: 5.23, h: H, sizing: { type: "cover", w: 5.23, h: H } });
  s.addShape(p.shapes.RECTANGLE, { x: 0, y: 0, w: 8.1, h: H, fill: { color: DARK, transparency: 8 } });
  s.addText([
    { text: "基于 PPO 的无人艇", options: { breakLine: true } },
    { text: "路径跟踪控制", options: {} },
  ], { x: 0.7, y: 1.85, w: 7.1, h: 1.7, fontSize: 40, fontFace: FONT, bold: true, color: ONDARK, margin: 0, paraSpaceAfter: 4 });
  s.addText("强化学习方案 C：建模 · 训练 · 验证 · 结果分析", { x: 0.7, y: 3.75, w: 7.2, h: 0.5, fontSize: 19, fontFace: FONT, color: ONDARK_MUT, margin: 0 });
  s.addText([
    { text: "组会汇报 · 2026-10-06", options: { breakLine: true } },
    { text: "汇报人: trevor    |    1.2 m 双推进器 USV · 10M 步 · VRX 仿真", options: {} },
  ], { x: 0.7, y: 6.1, w: 7.1, h: 0.8, fontSize: 14, fontFace: FONT, color: ONDARK_MUT, margin: 0, paraSpaceAfter: 6 });
  s.addNotes("开场: 本次汇报介绍无人艇路径跟踪的第三条控制路线——强化学习方案C。前面方案A/B是MPC, 方案C用PPO离线训练、在线只做0.03毫秒推理。汇报四部分: 脉络、算法设计、仿真验证、结果分析。所有数字都可溯源, 备份页有出处清单。");
})();

// ============ S2 提纲 ============
(() => {
  const s = slide();
  header(s, "", "汇报提纲", "四部分 · 约 20 分钟");
  const items = [
    ["01", "研究脉络", "任务定义 · 三条控制方案的定位\n为什么引入强化学习"],
    ["02", "算法设计", "MDP 建模: 观测 / 动作 / 奖励\n课程学习与域随机化 · PPO 配置"],
    ["03", "仿真验证", "五轮 reward hacking 攻防\n训练曲线 · 一致性验证协议"],
    ["04", "结果分析", "v5 vs LOS 基线 50 episode\n赢在哪 / 代价是什么 / 慎读什么"],
  ];
  const cw = 2.95, gap = 0.18, x0 = M;
  items.forEach(([n, t, d], i) => {
    const x = x0 + i * (cw + gap);
    card(s, x, 1.9, cw, 3.6, i === 3 ? "F5EBE2" : TINT);
    s.addText(n, { x: x + 0.25, y: 2.15, w: 1.6, h: 0.9, fontSize: 44, fontFace: FONT, bold: true, color: i === 3 ? ACCENT : PRIMARY, margin: 0 });
    s.addText(t, { x: x + 0.25, y: 3.1, w: cw - 0.5, h: 0.5, fontSize: 20, fontFace: FONT, bold: true, color: TEXT, margin: 0 });
    s.addText(d, { x: x + 0.25, y: 3.7, w: cw - 0.5, h: 1.5, fontSize: 13, fontFace: FONT, color: MUTED, margin: 0, paraSpaceAfter: 6 });
  });
  s.addNotes("四部分。重点在第二和第四部分: 算法设计的核心是奖励函数和五轮reward hacking攻防; 结果分析会同时讲赢的一面和代价的一面。");
})();

// ============ S3 问题定义与方案定位 ============
(() => {
  const s = slide();
  header(s, "01 · 脉络", "任务定义与三条控制方案", "1.2 m / 14.2 kg 双推进器(差动)USV · 5 Hz 控制 · 推力限幅 ±25 N");
  card(s, M, 1.55, 6.1, 2.5, "FFFFFF");
  s.addText("任务: 路径跟踪", { x: M + 0.3, y: 1.75, w: 5.5, h: 0.4, fontSize: 17, fontFace: FONT, bold: true, color: PRIMARY, margin: 0 });
  s.addText([
    { text: "沿规划器给定的参考路径航行: 几何(圆弧倒角样条) + 速度剖面(TOPP 简化版)", options: { bullet: bu(), breakLine: true } },
    { text: "评价指标: 横向误差 / 航向误差 / 成功率 / 能耗", options: { bullet: bu(), breakLine: true } },
    { text: "仿真: VRX Gazebo, 船模按实船辨识参数生成(数字孪生)", options: { bullet: bu() } },
  ], { x: M + 0.3, y: 2.2, w: 5.5, h: 1.7, fontSize: 13.5, fontFace: FONT, color: TEXT, margin: 0, paraSpaceAfter: 8 });
  const plans = [
    ["方案 A · 运动学 MPC", "C++ 实现, 已上实船 (Pi5)", TINT],
    ["方案 B · 动力学 NMPC", "acados SQP_RTI, 本汇报的对比基准", TINT],
    ["方案 C · 强化学习 PPO", "离线训练, 在线纯推理 — 本次汇报", "F5EBE2"],
  ];
  plans.forEach(([t, d, f], i) => {
    const y = 1.55 + i * 1.06;
    card(s, 7.0, y, 5.83, 0.92, f);
    s.addText(t, { x: 7.3, y: y + 0.12, w: 5.3, h: 0.35, fontSize: 15.5, fontFace: FONT, bold: true, color: i === 2 ? ACCENT : TEXT, margin: 0 });
    s.addText(d, { x: 7.3, y: y + 0.5, w: 5.3, h: 0.32, fontSize: 12.5, fontFace: FONT, color: MUTED, margin: 0 });
  });
  s.addText("为什么引入 RL:  MPC 依赖模型精度且每个控制拍在线求解(百毫秒级); RL 把计算搬到离线, 在线只剩一次神经网络前向(0.03 ms), 且有机会学到 MPC 难以显式建模的补偿行为。",
    { x: M, y: 4.5, w: 12.33, h: 0.75, fontSize: 14, fontFace: FONT, color: TEXT, margin: 0 });
  s.addImage({ path: "/home/trevor/USV/usv_mpc_ws/artifacts/vrx_model/preview.png", x: 8.6, y: 4.9, w: 3.7, h: 2.13, sizing: { type: "contain", w: 3.7, h: 2.13 } });
  s.addText("VRX 数字孪生船模", { x: 8.6, y: 7.05, w: 3.7, h: 0.3, fontSize: 11, fontFace: FONT, color: MUTED, align: "center", margin: 0 });
  srcLine(s, "usv_mpc_ws/README.md · usv_rl/README.md", 5.6);
  s.addNotes("任务本身: 一条带速度剖面的参考路径, 跟踪它。方案A已经上过实船; 方案B是动力学NMPC, 是方案C的对比基准; 方案C与B共用完全相同的话题接口, 所以看门狗和安全节点零改动就能切换。引入RL的动机: 在线计算量从每拍求解优化问题降到一次前向推理。");
})();

// ============ S4 总体链路 (原生形状) ============
(() => {
  const s = slide();
  header(s, "01 · 脉络", "方案 C 总体链路: 离线训练 → 导出 → 在线部署");
  const blocks = [
    ["训练侧 (离线)", "Gymnasium 环境\nFossen 3-DOF · RK4×4\nSB3 PPO · 16 并行环境\n10M 步 · 约 38 min", PRIMARY],
    ["导出", "策略网络 → ONNX\nVecNormalize 折叠进图\n输出物理推力 (N)\nSHA256 契约清单", "156B60"],
    ["部署侧 (在线)", "rl_policy_node\nONNX Runtime 推理\n0.03 ms / 拍\n与方案 B 同话题接口", "1E7A6B"],
  ];
  blocks.forEach(([t, d, c], i) => {
    const x = M + i * 4.35;
    s.addShape(p.shapes.ROUNDED_RECTANGLE, { x, y: 2.0, w: 3.5, h: 2.7, fill: { color: c }, rectRadius: 0.08, shadow: shadow() });
    s.addText(t, { x: x + 0.25, y: 2.2, w: 3.0, h: 0.45, fontSize: 18, fontFace: FONT, bold: true, color: ONDARK, margin: 0 });
    s.addText(d, { x: x + 0.25, y: 2.75, w: 3.0, h: 1.8, fontSize: 13.5, fontFace: FONT, color: ONDARK, margin: 0, paraSpaceAfter: 5 });
    if (i < 2) s.addText("→", { x: x + 3.52, y: 3.05, w: 0.85, h: 0.6, fontSize: 30, fontFace: FONT, bold: true, color: MUTED, align: "center", margin: 0 });
  });
  card(s, M, 5.2, 12.33, 1.5, "FFFFFF");
  s.addText("链路上的一致性门禁", { x: M + 0.3, y: 5.38, w: 4.0, h: 0.35, fontSize: 14.5, fontFace: FONT, bold: true, color: PRIMARY, margin: 0 });
  s.addText([
    { text: "M1 动力学对拍: Python 环境与 C++ 黄金参考 200 步逐点一致 (atol = rtol = 1e-8)", options: { bullet: bu(), breakLine: true } },
    { text: "M2 环境与链路: 17 项测试 — Gym API / 观测构造训练-部署等价 / 推力限幅语义 / ONNX 导出对拍 < 1e-3 N", options: { bullet: bu() } },
  ], { x: M + 0.3, y: 5.78, w: 11.7, h: 0.85, fontSize: 13, fontFace: FONT, color: TEXT, margin: 0, paraSpaceAfter: 6 });
  s.addNotes("三个环节。关键设计是'一致性门禁': 训练用的动力学和C++实船模型逐点对拍, 观测构造在训练环境和部署节点是同一份代码, 导出的ONNX用独立oracle验证。这保证训练的东西和部署的东西是同一个东西。");
})();

// ============ S5 观测空间 ============
(() => {
  const s = slide();
  header(s, "02 · 算法", "MDP 建模 ①: 43 维相对观测");
  s.addText("43", { x: M, y: 1.7, w: 2.6, h: 1.6, fontSize: 88, fontFace: FONT, bold: true, color: PRIMARY, margin: 0 });
  s.addText("维 float32\n无绝对 x, y", { x: M + 0.05, y: 3.35, w: 2.5, h: 0.8, fontSize: 14, fontFace: FONT, color: MUTED, margin: 0 });
  const rows = [
    ["本体速度 u, v, r", "3", "纵荡/横荡速度与艏摇角率"],
    ["艏向 sin ψ, cos ψ", "2", "自身朝向"],
    ["艏向误差 sin, cos", "2", "相对时间调度参考点"],
    ["调度剖面 v_ref, r_ref", "2", "当前时刻参考速度与角速度"],
    ["8 个前视点 × 4", "32", "体轴相对位置(2)+曲率+速度, 弧距 0.4–4.0 m"],
    ["上拍实际推力", "2", "执行器状态记忆"],
  ];
  const tbl = [[
    { text: "块", options: { fill: { color: PRIMARY }, color: "FFFFFF", bold: true } },
    { text: "维数", options: { fill: { color: PRIMARY }, color: "FFFFFF", bold: true } },
    { text: "含义", options: { fill: { color: PRIMARY }, color: "FFFFFF", bold: true } },
  ]].concat(rows.map(([a, b, c], i) => [
    { text: a, options: { fill: { color: i % 2 ? "FFFFFF" : TINT } } },
    { text: b, options: { fill: { color: i % 2 ? "FFFFFF" : TINT }, bold: true, color: PRIMARY } },
    { text: c, options: { fill: { color: i % 2 ? "FFFFFF" : TINT } } },
  ]));
  s.addTable(tbl, { x: 3.3, y: 1.65, w: 9.5, colW: [3.0, 0.9, 5.6], fontSize: 12.5, fontFace: FONT, color: TEXT, border: { pt: 0.5, color: BORDER }, rowH: 0.52, valign: "middle", margin: 0.08 });
  card(s, 3.3, 5.6, 9.5, 1.15, "FFFFFF");
  s.addText([
    { text: "设计要点", options: { bold: true, color: PRIMARY, breakLine: true } },
    { text: "全程相对量 → 平移不变, 每 episode 全局航向随机; 观测构造在训练环境与部署节点共用同一实现, 测试锁定逐维等价。", options: {} },
  ], { x: 3.6, y: 5.75, w: 8.9, h: 0.9, fontSize: 13, fontFace: FONT, color: TEXT, margin: 0, paraSpaceAfter: 4 });
  srcLine(s, "usv_tracking_env.py:124 · observation.py (训练/部署共用)", 6.95);
  s.addNotes("观测分6块共43维。两个刻意的设计: 一是不给绝对坐标, 只给体轴相对量, 平移不变, 航向每回合随机化, 防止策略记忆场地; 二是8个前视点让策略'看得见'前方路径几何。观测构造代码训练和部署共用, 有测试锁定等价。");
})();

// ============ S6 动作空间 ============
(() => {
  const s = slide();
  header(s, "02 · 算法", "MDP 建模 ②: 动作空间与执行语义");
  card(s, M, 1.7, 6.6, 4.0, "FFFFFF");
  s.addText("动作到推力的映射", { x: M + 0.3, y: 1.9, w: 5.5, h: 0.4, fontSize: 16, fontFace: FONT, bold: true, color: PRIMARY, margin: 0 });
  s.addText([
    { text: "a ∈ [-1, 1]^2   (策略输出)", options: { breakLine: true } },
    { text: "        ↓  × t_max = 25 N", options: { breakLine: true } },
    { text: "原始推力 [-25, +25] N", options: { breakLine: true } },
    { text: "        ↓  变化率限制 80 N/s → 16 N/拍 (dt = 0.2 s)", options: { breakLine: true } },
    { text: "下拍实际推力 T_L, T_R", options: {} },
  ], { x: M + 0.4, y: 2.4, w: 5.9, h: 2.4, fontSize: 15, fontFace: FONT, color: TEXT, margin: 0, paraSpaceAfter: 8 });
  s.addText("±25 N", { x: M + 0.4, y: 4.85, w: 2.6, h: 0.7, fontSize: 40, fontFace: FONT, bold: true, color: PRIMARY, margin: 0 });
  s.addText("每拍最大变化 16 N", { x: M + 3.1, y: 5.0, w: 3.2, h: 0.5, fontSize: 15, fontFace: FONT, color: MUTED, margin: 0, valign: "middle" });
  card(s, 7.5, 1.7, 5.33, 4.0, "F5EBE2");
  s.addText("为什么必须归一化?", { x: 7.8, y: 1.9, w: 4.7, h: 0.4, fontSize: 16, fontFace: FONT, bold: true, color: ACCENT, margin: 0 });
  s.addText([
    { text: "早期版本直接输出 ±25 N 物理量纲", options: { bullet: bu(), breakLine: true } },
    { text: "PPO 初始探索噪声 std = 1 → 探索只覆盖量程的 4%", options: { bullet: bu(), breakLine: true } },
    { text: "策略学不会大胆用推力, 只敢 ±1 N 微调 → 悬停蹭调度 rebase", options: { bullet: bu(), breakLine: true } },
    { text: "归一化到 [-1,1] 后, 同样的探索噪声覆盖全量程 (五轮攻防第 4 轮的教训)", options: { bullet: bu() } },
  ], { x: 7.8, y: 2.4, w: 4.75, h: 3.1, fontSize: 13.5, fontFace: FONT, color: TEXT, margin: 0, paraSpaceAfter: 8 });
  srcLine(s, "usv_tracking_env.py:126-216 · configs/env.yaml (t_max=25, d_t_max=80, dt=0.2)", 5.95);
  s.addNotes("动作2维, 对应左右推进器。归一化这一页是实战教训: 物理量纲做动作空间, PPO的探索噪声std=1在25N量程下只覆盖4%, 策略根本不敢用推力。归一化后训练才正常。变化率限制和部署侧执行语义逐位一致。");
})();

// ============ S7 奖励函数 ============
(() => {
  const s = slide();
  header(s, "02 · 算法", "MDP 建模 ③: 奖励函数 — 与 MPC 代价同源");
  card(s, M, 1.6, 7.3, 2.35, "FFFFFF");
  s.addText([
    { text: "r = - 0.2 · cost  +  15 · Δs_prog  ±  10 (终端)", options: { bold: true, fontSize: 16.5, breakLine: true } },
    { text: "cost = 20·e_x² + 20·e_y² + 100·e_sp² + 50·e_ψ²", options: { breakLine: true } },
    { text: "         + 8·(u-u_ref)² + 1·v² + 8·(r-r_ref)²", options: { breakLine: true } },
    { text: "         + 0.05·ΣT² + 0.2·ΣΔT²      (误差均封顶)", options: {} },
  ], { x: M + 0.35, y: 1.8, w: 6.7, h: 1.95, fontSize: 14.5, fontFace: FONT, color: TEXT, margin: 0, paraSpaceAfter: 6 });
  card(s, M, 4.15, 7.3, 2.5, TINT);
  s.addText("两个关键设计", { x: M + 0.3, y: 4.32, w: 4.0, h: 0.4, fontSize: 15, fontFace: FONT, bold: true, color: PRIMARY, margin: 0 });
  s.addText([
    { text: "调度 rebase ±2 m: 沿迹落后超阈值就把时间参考拉回船附近 — MPC 重规划语义, 杜绝「反正追不上不如躺平吃罚」", options: { bullet: bu(), breakLine: true } },
    { text: "空间最近点项 q=100: 与调度项分离的独立权重, 压过「抄直线赛车线」的进度收益 (v4→v5 的修复)", options: { bullet: bu(), breakLine: true } },
    { text: "终端奖惩 ±10: 走完全程有奖, 让「活到终点」比「早死止损」更划算 (v1 的修复)", options: { bullet: bu() } },
  ], { x: M + 0.3, y: 4.75, w: 6.75, h: 1.8, fontSize: 12.5, fontFace: FONT, color: TEXT, margin: 0, paraSpaceAfter: 7 });
  const wrows = [
    ["位置(调度/空间)", "20 / 100"], ["艏向", "50"], ["速度 u / 横荡 v / 角速率 r", "8 / 1 / 8"],
    ["推力能量 / 平滑", "0.05 / 0.2"], ["进度 / 终端", "15 / ±10"],
  ];
  const wtbl = [[
    { text: "权重项", options: { fill: { color: PRIMARY }, color: "FFFFFF", bold: true } },
    { text: "取值", options: { fill: { color: PRIMARY }, color: "FFFFFF", bold: true } },
  ]].concat(wrows.map(([a, b], i) => [
    { text: a, options: { fill: { color: i % 2 ? "FFFFFF" : TINT } } },
    { text: b, options: { fill: { color: i % 2 ? "FFFFFF" : TINT }, bold: true, color: PRIMARY, align: "center" } },
  ]));
  s.addText("Q/R/Rd 与 MPC 参数同源", { x: 8.2, y: 1.65, w: 4.6, h: 0.35, fontSize: 14.5, fontFace: FONT, bold: true, color: TEXT, margin: 0 });
  s.addTable(wtbl, { x: 8.2, y: 2.1, w: 4.6, colW: [3.1, 1.5], fontSize: 12.5, fontFace: FONT, color: TEXT, border: { pt: 0.5, color: BORDER }, rowH: 0.5, valign: "middle", margin: 0.08 });
  s.addText("奖励 = 负 MPC 代价 + 进度 + 终端 → RL 与 MPC 优化同一个目标, 对比才公平", { x: 8.2, y: 5.35, w: 4.6, h: 1.2, fontSize: 12.5, fontFace: FONT, color: MUTED, margin: 0 });
  srcLine(s, "configs/env.yaml:19-43 (w_progress=15, q_pos_spatial=100) · mpc_params.yaml");
  s.addNotes("奖励函数是这次工作的核心。基座是MPC的代价函数, 权重同源——这样RL和MPC是在优化同一个目标, 结果可比。真正的设计难点在三个修正: rebase防止躺平, 空间项防抄近道, 终端奖惩防自尽。这三个修正分别对应后面五轮攻防的三轮。");
})();

// ============ S8 课程学习 + 域随机化 ============
(() => {
  const s = slide();
  header(s, "02 · 算法", "课程学习与域随机化", "权重与归一化统计全程延续, 仅环境按阶段切换");
  const stages = [
    ["s1 直线", "1M 步", "先学会贴线前进"],
    ["s2 折线", "2M 步", "连续转向"],
    ["s3 随机", "3M 步", "4–7 段随机曲率, 泛化"],
    ["s4 +DR", "4M 步", "扰动下训练, 面向实船"],
  ];
  stages.forEach(([t, n, d], i) => {
    const x = M + i * 3.12;
    card(s, x, 1.75, 2.9, 1.9, i === 3 ? "F5EBE2" : "FFFFFF");
    s.addText(t, { x: x + 0.22, y: 1.95, w: 2.4, h: 0.4, fontSize: 16.5, fontFace: FONT, bold: true, color: i === 3 ? ACCENT : PRIMARY, margin: 0 });
    s.addText(n, { x: x + 0.22, y: 2.4, w: 2.4, h: 0.35, fontSize: 13, fontFace: FONT, bold: true, color: TEXT, margin: 0 });
    s.addText(d, { x: x + 0.22, y: 2.8, w: 2.5, h: 0.6, fontSize: 12, fontFace: FONT, color: MUTED, margin: 0 });
    if (i < 3) s.addText("→", { x: x + 2.86, y: 2.35, w: 0.3, h: 0.5, fontSize: 20, fontFace: FONT, color: MUTED, align: "center", margin: 0 });
  });
  s.addText("s4 域随机化参数", { x: M, y: 4.0, w: 5.0, h: 0.4, fontSize: 15.5, fontFace: FONT, bold: true, color: TEXT, margin: 0 });
  const drs = [
    ["水动力参数", "19 参数各自独立 ×U(0.8, 1.2)"],
    ["推力执行延迟", "每回合 0–1 拍随机"],
    ["观测噪声", "速度 σ=0.02, 位置 σ=0.05"],
    ["初始扰动", "位置 ±0.3 m, 艏向 ±0.3 rad"],
  ];
  drs.forEach(([t, d], i) => {
    const x = M + (i % 2) * 6.3, y = 4.5 + Math.floor(i / 2) * 1.05;
    card(s, x, y, 6.05, 0.9, "FFFFFF");
    s.addText(t, { x: x + 0.28, y: y + 0.1, w: 2.4, h: 0.35, fontSize: 13.5, fontFace: FONT, bold: true, color: PRIMARY, margin: 0 });
    s.addText(d, { x: x + 2.6, y: y + 0.1, w: 3.3, h: 0.65, fontSize: 12.5, fontFace: FONT, color: TEXT, margin: 0, valign: "middle" });
  });
  s.addText("评估恒定关闭 DR (干净条件下的真实水平); 随机世界航向与初始扰动每回合生效", { x: M, y: 6.65, w: 12.0, h: 0.35, fontSize: 12.5, fontFace: FONT, color: MUTED, margin: 0 });
  srcLine(s, "configs/ppo.yaml:37-57 · usv_tracking_env.py reset()/dynamics.py:67-73");
  s.addNotes("课程从易到难四阶段, 共一千万步。s4加域随机化是sim-to-real的桥: 让策略在训练时见过水动力不准、执行有延迟、观测有噪的情况。注意评估时恒定关DR, 否则数字没法和基线比。");
})();

// ============ S9 PPO 一页 ============
(() => {
  const s = slide();
  header(s, "02 · 算法", "PPO 与训练配置一页");
  card(s, M, 1.65, 6.3, 3.0, "FFFFFF");
  s.addText("PPO-Clip 目标", { x: M + 0.3, y: 1.82, w: 4.0, h: 0.4, fontSize: 15.5, fontFace: FONT, bold: true, color: PRIMARY, margin: 0 });
  s.addText([
    { text: "L = E[ min( r_t·A_t,  clip(r_t, 1±0.2)·A_t ) ]", options: { bold: true, fontSize: 15, breakLine: true } },
    { text: "r_t = π_new(a|s) / π_old(a|s),  A_t: GAE(γ=0.99, λ=0.95)", options: { fontSize: 12.5, breakLine: true } },
    { text: "概率比裁剪在 [0.8, 1.2] → 单次更新不会把策略改崩", options: { fontSize: 12.5, breakLine: true } },
    { text: "网络: 256×256 tanh MLP, 策略头 + 价值头", options: { fontSize: 12.5 } },
  ], { x: M + 0.3, y: 2.3, w: 5.8, h: 2.2, fontSize: 13.5, fontFace: FONT, color: TEXT, margin: 0, paraSpaceAfter: 7 });
  card(s, M, 4.85, 6.3, 1.8, TINT);
  s.addText([
    { text: "为什么选 PPO", options: { bold: true, color: PRIMARY, breakLine: true } },
    { text: "连续动作 + 一阶方法 + 对超参不敏感 + SB3 成熟实现; 相比 SAC 样本效率略低但稳定性好, 适合小团队迭代。", options: {} },
  ], { x: M + 0.3, y: 5.05, w: 5.8, h: 1.4, fontSize: 13, fontFace: FONT, color: TEXT, margin: 0, paraSpaceAfter: 5 });
  const cfg = [
    ["并行环境 / 总步数", "16 / 10M"], ["rollout (n_steps×16)", "2048 → 32768"],
    ["minibatch × epoch", "4096 × 10"], ["学习率", "3e-4 线性退火"],
    ["γ / λ / clip", "0.99 / 0.95 / 0.2"], ["熵系数", "0.005"],
    ["随机种子 / 墙钟", "42 / ≈38 min"],
  ];
  const ct = [[
    { text: "配置", options: { fill: { color: PRIMARY }, color: "FFFFFF", bold: true } },
    { text: "取值", options: { fill: { color: PRIMARY }, color: "FFFFFF", bold: true } },
  ]].concat(cfg.map(([a, b], i) => [
    { text: a, options: { fill: { color: i % 2 ? "FFFFFF" : TINT } } },
    { text: b, options: { fill: { color: i % 2 ? "FFFFFF" : TINT }, bold: true, color: PRIMARY } },
  ]));
  s.addTable(ct, { x: 7.2, y: 1.65, w: 5.6, colW: [3.3, 2.3], fontSize: 12.5, fontFace: FONT, color: TEXT, border: { pt: 0.5, color: BORDER }, rowH: 0.52, valign: "middle", margin: 0.08 });
  s.addText("VecNormalize: 观测/奖励运行归一化, 统计全程延续, 部署随 ONNX 一并带走", { x: 7.2, y: 6.1, w: 5.6, h: 0.6, fontSize: 12, fontFace: FONT, color: MUTED, margin: 0 });
  srcLine(s, "configs/ppo.yaml · train.py · artifacts/rl_models/v5/s4_dr/train_meta.json (wall 2281.5 s)");
  s.addNotes("PPO一句话: 概率比裁剪让每次策略更新保守, GAE算优势。配置是标准连续控制配方: 大缓冲区求稳, 学习率线性退火。整个训练只要38分钟墙钟, 16环境并行, 这是纯Python动力学便宜的地方, 也是敢于五轮迭代的前提。");
})();

// ============ S10 五轮攻防 上 ============
(() => {
  const s = slide();
  header(s, "03 · 验证", "五轮 reward hacking 攻防 (上)", "每一轮: 策略找到激励漏洞 → 修激励结构, 不修策略");
  const rows = [
    ["v1", "倒车「自尽」, ep_len 只有 23 步", "存活罚 >> 速死罚 → 死比活便宜 8.5 倍", "调度 rebase + 终端奖惩 ±10"],
    ["v2", "以 0.24 m 精度沿路径「精确倒车」", "前进收益 ≈ 死亡收益, 倒车也能贴线吃误差罚的减少", "进度权重 0.5 → 15"],
    ["v3", "ep_len 303 → ≈29 步单调衰减", "提前终止成了「速死止损通道」", "训练期取消提前终止 + 动作归一化"],
  ];
  rows.forEach(([v, sym, cause, fix], i) => {
    const y = 1.75 + i * 1.62;
    card(s, M, y, 12.33, 1.45, i % 2 ? TINT : "FFFFFF");
    s.addText(v, { x: M + 0.25, y: y + 0.35, w: 1.0, h: 0.75, fontSize: 30, fontFace: FONT, bold: true, color: MUTED, margin: 0 });
    s.addText([{ text: "症状: ", options: { bold: true, color: ACCENT } }, { text: sym, options: {} }],
      { x: M + 1.35, y: y + 0.14, w: 11.0, h: 0.4, fontSize: 13.5, fontFace: FONT, color: TEXT, margin: 0 });
    s.addText([{ text: "根因: ", options: { bold: true } }, { text: cause, options: {} }],
      { x: M + 1.35, y: y + 0.57, w: 11.0, h: 0.4, fontSize: 13, fontFace: FONT, color: TEXT, margin: 0 });
    s.addText([{ text: "修复: ", options: { bold: true, color: PRIMARY } }, { text: fix, options: {} }],
      { x: M + 1.35, y: y + 1.0, w: 11.0, h: 0.4, fontSize: 13, fontFace: FONT, color: TEXT, margin: 0 });
  });
  srcLine(s, "usv_rl/README.md 五轮迭代表 · commits 0590ac1 / d1b3408 / 4d69b69", 6.8);
  s.addNotes("五轮攻防是这轮工作最有价值的部分。v1策略发现早死比活着便宜; v2发现倒车也能贴线; v3发现训练器会给'活不下去'的策略提前终止——终止条件本身成了求死通道。每一轮的修法都是改激励结构, 不是惩罚策略。");
})();

// ============ S11 五轮攻防 下 ============
(() => {
  const s = slide();
  header(s, "03 · 验证", "五轮 reward hacking 攻防 (下)");
  const rows = [
    ["v4", "悬停不动, 反复蹭 rebase 吃进度", "±25 N 量纲下 PPO 探索只有 ±1 N (4% 量程)", "动作空间归一化 [-1,1]"],
    ["v5", "直线切弯 / 赛车线甩宽 (13.6 m)", "rebase 释放几何自由度 + 2 m 封顶使大偏差梯度饱和", "空间最近点惩罚独立权重 100"],
  ];
  rows.forEach(([v, sym, cause, fix], i) => {
    const y = 1.7 + i * 1.6;
    card(s, M, y, 12.33, 1.42, i % 2 ? TINT : "FFFFFF");
    s.addText(v, { x: M + 0.25, y: y + 0.33, w: 1.0, h: 0.75, fontSize: 30, fontFace: FONT, bold: true, color: MUTED, margin: 0 });
    s.addText([{ text: "症状: ", options: { bold: true, color: ACCENT } }, { text: sym, options: {} }],
      { x: M + 1.35, y: y + 0.13, w: 11.0, h: 0.4, fontSize: 13.5, fontFace: FONT, color: TEXT, margin: 0 });
    s.addText([{ text: "根因: ", options: { bold: true } }, { text: cause, options: {} }],
      { x: M + 1.35, y: y + 0.55, w: 11.0, h: 0.4, fontSize: 13, fontFace: FONT, color: TEXT, margin: 0 });
    s.addText([{ text: "修复: ", options: { bold: true, color: PRIMARY } }, { text: fix, options: {} }],
      { x: M + 1.35, y: y + 0.97, w: 11.0, h: 0.4, fontSize: 13, fontFace: FONT, color: TEXT, margin: 0 });
  });
  card(s, M, 5.0, 12.33, 1.85, "F5EBE2");
  s.addText("五条方法论教训", { x: M + 0.3, y: 5.15, w: 4.0, h: 0.35, fontSize: 14.5, fontFace: FONT, bold: true, color: ACCENT, margin: 0 });
  s.addText([
    { text: "激励结构要保证「活比死好、前进比倒车好、贴线比抄近道好」的偏序, 再谈调参", options: { bullet: bu(), breakLine: true } },
    { text: "终止条件、封顶、rebase 这类「善意机制」都可能被当成通道 — 改一处要重看全局", options: { bullet: bu(), breakLine: true } },
    { text: "动作量纲决定探索覆盖; 每轮只动一个权重, 归因才干净 — 五轮共 5 个 commit, 每轮一个变量", options: { bullet: bu() } },
  ], { x: M + 0.3, y: 5.55, w: 11.7, h: 1.25, fontSize: 12.5, fontFace: FONT, color: TEXT, margin: 0, paraSpaceAfter: 6 });
  srcLine(s, "usv_rl/README.md · f256eb4 · 训练教程 rl_tutorial.md 第 9 章将五轮案例作为核心教材");
  s.addNotes("后两轮: 第4轮是量纲问题——25N量纲下探索只覆盖4%; 第5轮是rebase释放了几何自由度后, 误差封顶让远处偏差梯度饱和, 需要独立的空间项。总结成三条方法论: 偏序设计、警惕善意机制、单变量归因。这些教训已写进组内教程第9章。");
})();

// ============ S12 训练曲线主图 ============
(() => {
  const s = slide();
  header(s, "03 · 验证", "训练曲线: 五个版本的成败一线");
  s.addImage({ path: ASSETS + "/curves_success_cross_version.png", x: 0.92, y: 1.5, w: 11.5, h: 4.995 });
  s.addText([
    { text: "v1–v3 成功率恒为 0 — 自尽/倒车/悬停永远到不了终点", options: { bullet: bu(), breakLine: true } },
    { text: "v4/v5 在三次课程切换处 (1M/3M/6M) 可见瞬时跌落再恢复; v5→下一页看质量指标", options: { bullet: bu() } },
  ], { x: M, y: 6.62, w: 12.33, h: 0.5, fontSize: 12, fontFace: FONT, color: TEXT, margin: 0, paraSpaceAfter: 3 });
  srcLine(s, "artifacts/rl_runs/{v1..v5} TensorBoard rollout/success_rate (308 采样点/版本, 4 阶段合并)", 7.12);
  s.addNotes("这是主叙事图。绿线v5四十万步就在简单场景学会完成, 三次凹陷正好对应课程切换, 最后加DR短暂跌落再恢复。灰紫红线贴零——不是没收敛, 是被reward hacking卡死, 任务根本完成不了。");
})();

// ============ S13 收敛细节 ============
(() => {
  const s = slide();
  header(s, "03 · 验证", "收敛细节: v5 全程在线 / v3 的求死通道");
  s.addImage({ path: ASSETS + "/v5_convergence.png", x: M, y: 1.55, w: 6.4, h: 3.6 });
  s.addText("v5: 奖励与评估成功率 (右轴终点 1.00, 50 eps 复核)", { x: M, y: 5.2, w: 6.4, h: 0.3, fontSize: 12, fontFace: FONT, color: MUTED, margin: 0 });
  s.addImage({ path: ASSETS + "/v3_ep_len_decay.png", x: 7.15, y: 1.85, w: 5.7, h: 2.36 });
  s.addText("v3: 平均回合长度 303 → ≈29 步", { x: 7.15, y: 4.3, w: 5.7, h: 0.3, fontSize: 12, fontFace: FONT, color: MUTED, margin: 0 });
  card(s, 7.15, 4.85, 5.68, 1.8, "FFFFFF");
  s.addText([
    { text: "读图要点", options: { bold: true, color: PRIMARY, breakLine: true } },
    { text: "v5 评估成功率在 5M 步后稳定 1.0; s4 加入 DR 时奖励暂跌后恢复", options: { bullet: bu(), breakLine: true } },
    { text: "v3 的 ep_len 单调下行 = 策略在学「更快地死」— 激励结构问题的直接证据", options: { bullet: bu() } },
  ], { x: 7.45, y: 5.05, w: 5.1, h: 1.5, fontSize: 12.5, fontFace: FONT, color: TEXT, margin: 0, paraSpaceAfter: 5 });
  srcLine(s, "TensorBoard: rollout/ep_rew_mean · eval/success_rate · rollout/ep_len_mean");
  s.addNotes("左边v5: 上面的奖励曲线三次台阶对应课程, 评估成功率从5M步起稳定满分。右边v3是反面教材: 回合长度一路跌到29步, 策略在学怎么快点死。这张图后来成了教程里讲激励设计的标准案例。");
})();

// ============ S14 验证协议 ============
(() => {
  const s = slide();
  header(s, "03 · 验证", "仿真验证协议: 先证明「训练=部署」, 再比数字");
  const cards3 = [
    ["M1 · 动力学对拍", "Python 环境模型 vs C++ 实船模型\n200 步 RK4×4 逐点对比\natol = rtol = 1e-8\n19 参数经 CSV 以 17 位精度传递"],
    ["M2 · 环境与链路 (17 项)", "Gym API / 43 维空间 / 种子确定性\n推力限幅与变化率语义\n观测构造: 训练 ↔ 部署逐维等价\nLOS 基线可完成直线任务"],
    ["评估协议", "随机路径 50 episode\nDR 全关, deterministic\n指标: 成功率 / e_ct / e_ψ / 能耗\n汇报前重跑: 与 README 表一致"],
  ];
  cards3.forEach(([t, d], i) => {
    const x = M + i * 4.35;
    card(s, x, 1.8, 3.5, 3.4, i === 2 ? "F5EBE2" : TINT);
    s.addText(t, { x: x + 0.25, y: 2.0, w: 3.0, h: 0.5, fontSize: 15.5, fontFace: FONT, bold: true, color: i === 2 ? ACCENT : PRIMARY, margin: 0 });
    s.addText(d, { x: x + 0.25, y: 2.6, w: 3.05, h: 2.4, fontSize: 12.5, fontFace: FONT, color: TEXT, margin: 0, paraSpaceAfter: 6 });
  });
  card(s, M, 5.5, 12.33, 1.2, "FFFFFF");
  s.addText([
    { text: "为什么较真到 1e-8: ", options: { bold: true, color: PRIMARY } },
    { text: "训练环境若与实船模型有偏差, RL 会把模型误差学成「技能」; 逐位对拍保证策略学的是船, 不是仿真器的私货。", options: {} },
  ], { x: M + 0.3, y: 5.7, w: 11.7, h: 0.8, fontSize: 13.5, fontFace: FONT, color: TEXT, margin: 0, valign: "middle" });
  srcLine(s, "tests/test_dynamics_vs_cpp.py (M1) · tests/ 17 项 (M2) · evaluate.py (评估)");
  s.addNotes("验证协议三块。M1是最较真的部分: 训练环境和C++实船模型200步逐点1e-8一致。为什么这么较真——如果训练环境和部署模型有偏差, RL会把仿真器的私货学成技能。M2锁环境和链路; 最后评估协议固定50条随机路径关DR。");
})();

// ============ S15 结果 ============
(() => {
  const s = slide();
  header(s, "04 · 结果", "v5 评估结果: PPO vs LOS+PD 基线");
  s.addImage({ path: ASSETS + "/results_bar.png", x: 0.62, y: 1.55, w: 12.1, h: 3.58 });
  const rows = [
    ["成功率", "100%", "100%", "持平"],
    ["横向误差 RMS", "0.404 m", "0.312 m", "-23%"],
    ["横向误差 max", "1.172 m", "1.056 m", "-10%"],
    ["航向误差 RMS", "25.8°", "16.1°", "-38%"],
    ["在线推理耗时", "-", "0.03 ms", "—"],
  ];
  const tbl = [[
    { text: "指标", options: { fill: { color: PRIMARY }, color: "FFFFFF", bold: true } },
    { text: "LOS+PD", options: { fill: { color: PRIMARY }, color: "FFFFFF", bold: true } },
    { text: "PPO v5", options: { fill: { color: PRIMARY }, color: "FFFFFF", bold: true } },
    { text: "变化", options: { fill: { color: PRIMARY }, color: "FFFFFF", bold: true } },
  ]].concat(rows.map(([a, b, c, d], i) => [
    { text: a, options: { fill: { color: i % 2 ? "FFFFFF" : TINT } } },
    { text: b, options: { fill: { color: i % 2 ? "FFFFFF" : TINT } } },
    { text: c, options: { fill: { color: i % 2 ? "FFFFFF" : TINT }, bold: true, color: PRIMARY } },
    { text: d, options: { fill: { color: i % 2 ? "FFFFFF" : TINT }, bold: true, color: d.startsWith("-") ? PRIMARY : MUTED } },
  ]));
  s.addTable(tbl, { x: M, y: 5.22, w: 8.2, colW: [2.6, 1.9, 1.9, 1.8], fontSize: 12, fontFace: FONT, color: TEXT, border: { pt: 0.5, color: BORDER }, rowH: 0.29, valign: "middle", margin: 0.04 });
  s.addText("成功率 100% 持平 →\n精度指标才有区分度", { x: 9.0, y: 5.45, w: 3.8, h: 1.2, fontSize: 12.5, fontFace: FONT, color: MUTED, margin: 0 });
  srcLine(s, "usv_rl/README.md v5 表 (随机路径 50 eps, DR off); 汇报前重跑复现一致", 7.12);
  s.addNotes("结果一页。四张柱图: 前三个精度指标PPO全面占优, 航向误差改善最大(-38%); 第四个能耗是代价, 下一页细讲。表格是README的v5表, 汇报前我重跑了50条路径, 数字逐项复现。");
})();

// ============ S16 结果分析 ============
(() => {
  const s = slide();
  header(s, "04 · 结果", "结果分析: 赢在哪 / 代价是什么 / 慎读什么");
  const cols = [
    ["赢在哪", PRIMARY, TINT, [
      "航向误差 RMS -38%: 转弯段更快对准参考艏向",
      "横向误差 RMS -23%: 中段贴线更紧 (见轨迹复演)",
      "决策耗时 0.03 ms, 为 MPC 方案的千分之一量级",
    ]],
    ["代价", ACCENT, "F5EBE2", [
      "能耗 ×3.0 (2416 → 7339 N²·s): 推力波动更大",
      "控制动作量 ×15.7 (115 → 1797 N/ep): 高频微调",
      "归因: r_dthrust=0.2 相对偏弱, 未惩罚高频分量",
    ]],
    ["慎读", MUTED, "FFFFFF", [
      "成功率均 100%, 此场景下无区分度",
      "CTE max 仅 -10%: 单回合峰值仍可达 1.05 m",
      "训练 rollout 含 DR, 与评估协议不同; 未记录 ep_len",
    ]],
  ];
  cols.forEach(([t, c, f, items], i) => {
    const x = M + i * 4.35;
    card(s, x, 1.75, 3.5, 4.6, f);
    s.addText(t, { x: x + 0.25, y: 1.95, w: 3.0, h: 0.45, fontSize: 17, fontFace: FONT, bold: true, color: c, margin: 0 });
    s.addText(items.map((it, j) => ({ text: it, options: { bullet: bu(), breakLine: j < items.length - 1 } })),
      { x: x + 0.25, y: 2.55, w: 3.05, h: 3.6, fontSize: 12.5, fontFace: FONT, color: TEXT, margin: 0, paraSpaceAfter: 10 });
  });
  srcLine(s, "README v5 表 · 本次复现评估 eval_{los,ppo_v5}_50eps.txt (能耗与平滑为本次新增指标)");
  s.addNotes("诚实的三栏。赢在精度和速度; 代价是能耗三倍、控制动作十五倍——策略用高频微调换贴线, 说明平滑权重偏弱, 这是下一步奖励再平衡的对象。慎读一栏: 成功率都满分没有区分度, 峰值误差改善有限, 这些话要自己先说, 不能等别人问。");
})();

// ============ S17 轨迹复演 ============
(() => {
  const s = slide();
  header(s, "04 · 结果", "轨迹复演: 同一条随机路径上的形态对比");
  s.addImage({ path: ASSETS + "/trajectory_replay.png", x: M, y: 1.55, w: 7.66, h: 5.5 });
  card(s, 8.5, 1.75, 4.33, 4.9, TINT);
  s.addText("读图", { x: 8.8, y: 1.95, w: 3.7, h: 0.4, fontSize: 15, fontFace: FONT, bold: true, color: PRIMARY, margin: 0 });
  s.addText([
    { text: "同一 seed → 两条轨迹跑同一条 45 m 随机路径", options: { bullet: bu(), breakLine: true } },
    { text: "中段连续弯: PPO (绿) 始终压着参考线内侧, LOS (灰) 外甩更明显", options: { bullet: bu(), breakLine: true } },
    { text: "LOS 尾段摆动振幅更大 (±50 cm); PPO 稳在 ±40 cm 内但带高频毛刺 — 与能耗结论一致", options: { bullet: bu(), breakLine: true } },
    { text: "此图为形态佐证; 统计结论以 50 episode 评估为准", options: { bullet: bu() } },
  ], { x: 8.8, y: 2.45, w: 3.75, h: 4.0, fontSize: 12.5, fontFace: FONT, color: TEXT, margin: 0, paraSpaceAfter: 9 });
  srcLine(s, "训练环境复演脚本 fig_trajectory.py (seed 9999, DR off) — 非 VRX bag 回放", 7.12);
  s.addNotes("轨迹形态对比。两条轨迹同一seed同一路径。看中段连续弯: PPO压线更紧, 这就是航向误差-38%的直观来源; 但注意PPO的误差曲线有小毛刺, 和能耗三倍是同一件事——高频微调。这张图是训练环境复演, 不是仿真bag。");
})();

// ============ S18 工程教训 ============
(() => {
  const s = slide();
  header(s, "04 · 结果", "一次真实的部署事故: ONNX 单位 bug", "训练完美的策略, 上船可能只有 ±1 N");
  const before = [
    ["修复前", "1.0 N", "VRX 中实际最大推力 (图输出 [-1,1] 被当作牛顿)", MUTED, "FFFFFF"],
    ["修复后", "20.15 N", "图内嵌 25×clip, 输出物理牛顿", PRIMARY, TINT],
  ];
  before.forEach(([t, n, d, c, f], i) => {
    const x = M + i * 4.35;
    card(s, x, 1.8, 3.5, 2.3, f);
    s.addText(t, { x: x + 0.25, y: 2.0, w: 3.0, h: 0.35, fontSize: 14, fontFace: FONT, bold: true, color: c, margin: 0 });
    s.addText(n, { x: x + 0.25, y: 2.4, w: 3.0, h: 0.85, fontSize: 40, fontFace: FONT, bold: true, color: c, margin: 0 });
    s.addText(d, { x: x + 0.25, y: 3.3, w: 3.05, h: 0.7, fontSize: 11.5, fontFace: FONT, color: MUTED, margin: 0 });
  });
  card(s, 9.2, 1.8, 3.63, 2.3, "F5EBE2");
  s.addText("均速变化", { x: 9.45, y: 2.0, w: 3.1, h: 0.35, fontSize: 14, fontFace: FONT, bold: true, color: ACCENT, margin: 0 });
  s.addText("0.267 → 0.861 m/s", { x: 9.45, y: 2.45, w: 3.2, h: 0.6, fontSize: 21, fontFace: FONT, bold: true, color: ACCENT, margin: 0 });
  s.addText("同一策略, 只修了导出链\n(CTE 0.117→0.147 m, 如实标注为回归)", { x: 9.45, y: 3.1, w: 3.2, h: 0.85, fontSize: 11.5, fontFace: FONT, color: MUTED, margin: 0 });
  card(s, M, 4.5, 12.33, 2.2, TINT);
  s.addText("现在的防线: 导出即契约", { x: M + 0.3, y: 4.68, w: 5.0, h: 0.4, fontSize: 15, fontFace: FONT, bold: true, color: PRIMARY, margin: 0 });
  s.addText([
    { text: "导出器: 图内嵌 25×clip + 配套 manifest (输出单位/维数/缩放/SHA256), 独立 oracle 对拍 ≤2e-5 N (容差 1e-3)", options: { bullet: bu(), breakLine: true } },
    { text: "部署节点: 加载时硬校验 manifest 与当前执行配置 (t_max=25 N), 任一不符 → 拒绝上线, STANDBY 零推力", options: { bullet: bu(), breakLine: true } },
    { text: "教训: 「训练侧正确」≠「部署侧正确」— 单位、量纲、归一化统计必须作为契约显式声明并双向校验", options: { bullet: bu() } },
  ], { x: M + 0.3, y: 5.15, w: 11.7, h: 1.5, fontSize: 12.5, fontFace: FONT, color: TEXT, margin: 0, paraSpaceAfter: 6 });
  srcLine(s, ".sgh-research/experiments/v5_scaling_fix_20261003/ · policy_physical_n.manifest.json");
  s.addNotes("这个事故值得单独一页: 审计发现部署的ONNX输出其实是[-1,1], 在VRX里最大推力只有1牛——船一直在怠速爬。修复后20牛, 均速翻了三倍。现在的防线是把单位量纲做成显式契约, 导出和部署双向校验, 不匹配就拒绝上线。");
})();

// ============ S19 局限与下一步 ============
(() => {
  const s = slide();
  header(s, "04 · 结果", "局限与下一步");
  const items = [
    ["① 模型链差距", "训练环境水动力与 VRX plant 仍有参数差 (Yr_dot / Nv_dot); 数字孪生对齐与 P0 数据契约 (发布端事件流) 进行中, 为 GP 标签与执行时序证据铺路"],
    ["② 控制品质再平衡", "能耗 ×3 / 动作量 ×15.7: 提高平滑权重 r_dthrust、考虑动作低通或变化率再收紧; 目标是不丢精度地压回能耗"],
    ["③ 评估深度", "当前 50 eps 随机路径; 计划补: 分路径类型分项统计、失败案例分析、训练期曲线与评估对照的持久化 artifact"],
    ["④ 实船验证", "部署链路与方案 B 同接口, 安全节点看门狗零改动; 下一步仿真全链路 (vrx scheme:=C) 稳定性长跑, 再上真船"],
  ];
  items.forEach(([t, d], i) => {
    const x = M + (i % 2) * 6.3, y = 1.75 + Math.floor(i / 2) * 2.45;
    card(s, x, y, 6.05, 2.25, i === 3 ? "F5EBE2" : TINT);
    s.addText(t, { x: x + 0.28, y: y + 0.18, w: 5.5, h: 0.4, fontSize: 15.5, fontFace: FONT, bold: true, color: i === 3 ? ACCENT : PRIMARY, margin: 0 });
    s.addText(d, { x: x + 0.28, y: y + 0.65, w: 5.5, h: 1.45, fontSize: 12.5, fontFace: FONT, color: TEXT, margin: 0 });
  });
  srcLine(s, "usv_mpc_ws/docs/research/ (2026-10-03 审计) · .sgh-research/ F1–F5 基线");
  s.addNotes("四件事。模型链差距是最影响'仿真数字到实船'的, 正在用数据契约和参数对齐解决; 第二是这页能耗问题的直接后续; 第三是评估深度; 第四步真船——部署侧和方案B同接口, 切换成本低。");
})();

// ============ S20 总结 (dark) ============
(() => {
  const s = slide(true);
  s.addText("总结", { x: M, y: 0.55, w: 4.0, h: 0.7, fontSize: 32, fontFace: FONT, bold: true, color: ONDARK, margin: 0 });
  const takes = [
    ["01", "建模", "43 维相对观测 + 与 MPC 同源的奖励 + 调度 rebase — 让 RL 与 MPC 优化同一个目标, 公平可比"],
    ["02", "攻防", "五轮 reward hacking: 激励结构的偏序设计是 RL 落地的真正难点, 每轮一个变量、逐轮归因"],
    ["03", "结果", "v5: 成功率 100% 持平, 航向误差 -38%, 横向误差 -23%; 代价能耗 ×3 — 在线推理仅 0.03 ms"],
  ];
  takes.forEach(([n, t, d], i) => {
    const y = 1.7 + i * 1.62;
    s.addText(n, { x: M, y: y, w: 1.1, h: 0.9, fontSize: 40, fontFace: FONT, bold: true, color: ONDARK_MUT, margin: 0 });
    s.addText(t, { x: 1.8, y: y + 0.05, w: 1.6, h: 0.5, fontSize: 20, fontFace: FONT, bold: true, color: ONDARK, margin: 0 });
    s.addText(d, { x: 3.5, y: y + 0.02, w: 9.3, h: 1.35, fontSize: 14.5, fontFace: FONT, color: ONDARK_MUT, margin: 0 });
    if (i < 2) s.addShape(p.shapes.LINE, { x: 1.8, y: y + 1.42, w: 11.0, h: 0, line: { color: "1E4A50", width: 0.75 } });
  });
  s.addText("下一步: 奖励再平衡 → 仿真长跑 → 真船", { x: M, y: 6.5, w: 12.0, h: 0.5, fontSize: 16, fontFace: FONT, bold: true, color: ONDARK, margin: 0 });
  s.addNotes("三句话收尾: 建模上和MPC同源保证可比; 攻防上五轮迭代换来的激励设计纪律; 结果上精度全面占优但能耗是诚实的代价。下一步三步走: 再平衡、长跑、真船。欢迎提问。");
})();

// ============ S21 备份1: 超参全表 ============
(() => {
  const s = slide();
  header(s, "备份", "备份: 环境与 PPO 超参全表");
  const env = [
    ["dt / RK4 子步", "0.2 s / 4"], ["推力上限 / 变化率", "±25 N / 80 N·s⁻¹"],
    ["前视弧距", "0.4–4.0 m (8 点)"], ["回合上限", "min(450 步, 参考时长+5 s)"],
    ["成功判据", "剩余弧长 < 0.75 m"], ["训练期提前终止", "关 (违规仅标记)"],
    ["误差封顶", "调度 3 m / ψ 90° / 空间 2 m"], ["rebase 阈值", "±2 m"],
  ];
  const ppo = [
    ["n_envs / 总步数", "16 / 10,000,000"], ["n_steps × n_envs", "2048 → 32768/轮"],
    ["batch / epochs", "4096 / 10"], ["学习率", "3e-4 线性退火至 0"],
    ["γ / GAE λ", "0.99 / 0.95"], ["clip / 熵系数", "0.2 / 0.005"],
    ["vf 系数 / 梯度裁剪", "0.5 / 0.5"], ["种子 / 墙钟", "42 / 2281.5 s"],
  ];
  const mk = (rows) => [[
    { text: rows[0][0] === "dt / RK4 子步" ? "环境 (env.yaml)" : "PPO (ppo.yaml)", options: { colspan: 2, fill: { color: PRIMARY }, color: "FFFFFF", bold: true } },
  ]].concat(rows.map(([a, b], i) => [
    { text: a, options: { fill: { color: i % 2 ? "FFFFFF" : TINT } } },
    { text: b, options: { fill: { color: i % 2 ? "FFFFFF" : TINT }, color: TEXT } },
  ]));
  s.addTable(mk(env), { x: M, y: 1.6, w: 6.0, colW: [3.4, 2.6], fontSize: 12, fontFace: FONT, color: TEXT, border: { pt: 0.5, color: BORDER }, rowH: 0.5, valign: "middle", margin: 0.06 });
  s.addTable(mk(ppo), { x: 6.85, y: 1.6, w: 6.0, colW: [3.4, 2.6], fontSize: 12, fontFace: FONT, color: TEXT, border: { pt: 0.5, color: BORDER }, rowH: 0.5, valign: "middle", margin: 0.06 });
  s.addText("注: 80 N·s⁻¹ 的上标字符若显示异常请见讲稿; 网络结构 [256,256] tanh, 策略/价值双头。", { x: M, y: 6.75, w: 12.0, h: 0.35, fontSize: 11.5, fontFace: FONT, color: MUTED, margin: 0 });
  s.addNotes("备份页: 全部超参。有人问细节时翻到这页。");
})();

// ============ S22 备份2: 数据来源 ============
(() => {
  const s = slide();
  header(s, "备份", "备份: 每个数字的出处");
  const rows = [
    ["v5 结果表 (成功率/CTE/航向)", "usv_rl/README.md 「训练成果」; 汇报前以 evaluate.py 50 eps 重跑复现一致"],
    ["能耗 / 平滑 (×3 / ×15.7)", "本次复现评估 eval_los_50eps.txt / eval_ppo_v5_50eps.txt"],
    ["训练曲线 / v3 ep_len", "artifacts/rl_runs/{v1..v5} TensorBoard (fig_curves.py 解析, 308 点/版本)"],
    ["轨迹复演", "fig_trajectory.py, 训练环境 seed 9999, DR off (非 VRX bag)"],
    ["ONNX 单位 bug 数字", ".sgh-research/experiments/v5_scaling_fix_20261003/ + manifest"],
    ["奖励权重 / 观测维数 / 配置", "configs/env.yaml / env 源码:124 / configs/ppo.yaml"],
    ["五轮攻防", "README 五轮迭代表 + commits 0590ac1 d1b3408 4d69b69 f256eb4"],
  ];
  const tbl = [[
    { text: "内容", options: { fill: { color: PRIMARY }, color: "FFFFFF", bold: true } },
    { text: "出处", options: { fill: { color: PRIMARY }, color: "FFFFFF", bold: true } },
  ]].concat(rows.map(([a, b], i) => [
    { text: a, options: { fill: { color: i % 2 ? "FFFFFF" : TINT }, bold: true } },
    { text: b, options: { fill: { color: i % 2 ? "FFFFFF" : TINT } } },
  ]));
  s.addTable(tbl, { x: M, y: 1.6, w: 12.33, colW: [4.2, 8.13], fontSize: 12, fontFace: FONT, color: TEXT, border: { pt: 0.5, color: BORDER }, rowH: 0.62, valign: "middle", margin: 0.08 });
  s.addText("图表与复现脚本: usv_rl/docs/report_assets/ (fig_curves.py · fig_trajectory.py · eval_*.txt)", { x: M, y: 6.6, w: 12.0, h: 0.35, fontSize: 11.5, fontFace: FONT, color: MUTED, margin: 0 });
  s.addNotes("每个数字都有出处。图表生成和评估脚本都在report_assets目录, 可复跑。");
})();

p.writeFile({ fileName: OUT }).then(() => console.log("WROTE " + OUT));
