#!/usr/bin/env python3
"""按 孙国华-7.31组会汇报 模板生成四主线组会汇报 PPT（Clone & fill 模式）。内容采用通俗版表述。"""
import math
from lxml import etree
from pptx import Presentation
from pptx.util import Emu, Pt, Inches
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR, MSO_AUTO_SIZE
from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR
from pptx.oxml.ns import qn

A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
SRC = '/home/trevor/USV/usv_mpc_ws/docs/report_20261011/template.pptx'
OUT = '/home/trevor/USV/usv_mpc_ws/docs/组会汇报_四条主线_20261011.pptx'

ACCENT1 = RGBColor(0x4F, 0x81, 0xBD)   # theme accent1
DK2 = RGBColor(0x1F, 0x49, 0x7D)       # theme dk2
TINT = RGBColor(0xE9, 0xEF, 0xF7)      # accent1 浅色
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

prs = Presentation(SRC)

# ---------- 基础工具（均沿用 skill Approach A 的写法） ----------
def delete_slide(prs, idx):
    sld = list(prs.slides._sldIdLst)[idx]
    prs.part.drop_rel(sld.get(qn('r:id')))
    prs.slides._sldIdLst.remove(sld)

def replace_in_paragraph(p, new_text):
    runs = p.runs
    if not runs:
        p.add_run().text = new_text
        return
    runs[0].text = new_text
    for r in runs[1:]:
        r._r.getparent().remove(r._r)

def add_shadow(rPr):
    eff = etree.SubElement(rPr, f'{{{A}}}effectLst')
    sh = etree.SubElement(eff, f'{{{A}}}outerShdw',
                          {'blurRad': '38100', 'dist': '19050', 'dir': '2700000',
                           'algn': 'tl', 'rotWithShape': '0'})
    c = etree.SubElement(sh, f'{{{A}}}schemeClr', {'val': 'dk1'})
    etree.SubElement(c, f'{{{A}}}alpha', {'val': '40000'})

def add_title(slide, text):
    tb = slide.shapes.add_textbox(Emu(-678029), Emu(947315), Emu(7264360), Emu(523220))
    tf = tb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = text
    r.font.size = Pt(28)
    r.font.bold = True
    add_shadow(r._r.get_or_add_rPr())

def add_body(slide, paras, x=0.95, y=1.82, w=11.5, h=0.5, sz=14, spc_after=400):
    """paras: list of [(text, bold), ...] 段落，模板式「加粗标签：内容」。"""
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.SHAPE_TO_FIT_TEXT
    for i, segs in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        pPr = p._p.get_or_add_pPr()
        spc = etree.SubElement(pPr, f'{{{A}}}spcAft')
        etree.SubElement(spc, f'{{{A}}}spcPts', {'val': str(spc_after)})
        for t, b in segs:
            r = p.add_run()
            r.text = t
            r.font.size = Pt(sz)
            r.font.bold = True if b else None
    return tb

def add_plain_table(slide, rows, x, y, col_in, row_h_in, sz=16, sz_hdr=None):
    """模板式无边框居中表格（tblPr 无样式、tcPr 锚点居中）。"""
    n_r, n_c = len(rows), len(rows[0])
    gf = slide.shapes.add_table(n_r, n_c, Inches(x), Inches(y),
                                Inches(sum(col_in)), Inches(row_h_in * n_r))
    tbl = gf.table
    tblPr = tbl._tbl.tblPr
    for child in list(tblPr):
        tblPr.remove(child)
    for i, cw in enumerate(col_in):
        tbl.columns[i].width = Inches(cw)
    for j in range(n_r):
        tbl.rows[j].height = Inches(row_h_in)
    for j, row in enumerate(rows):
        for i, txt in enumerate(row):
            cell = tbl.cell(j, i)
            cell.margin_left = cell.margin_right = Emu(90519)
            cell.margin_top = cell.margin_bottom = Emu(45260)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            p = cell.text_frame.paragraphs[0]
            p.alignment = PP_ALIGN.CENTER
            etree.SubElement(p._p.get_or_add_pPr(), f'{{{A}}}buNone')
            r = p.add_run()
            r.text = txt
            r.font.size = Pt(sz_hdr if (j == 0 and sz_hdr) else sz)
            if j == 0 and sz_hdr:
                r.font.bold = True
    return gf

def box(slide, x, y, w, h, fill, lines, txt_color=WHITE):
    """圆角矩形 + 居中多行文本（架构图节点）。lines: [(text, sz, bold)]"""
    sh = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                Inches(x), Inches(y), Inches(w), Inches(h))
    try:
        sh.adjustments[0] = 0.10
    except Exception:
        pass
    sh.fill.solid()
    sh.fill.fore_color.rgb = fill
    sh.line.fill.background()
    sh.shadow.inherit = False
    tf = sh.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    for i, (t, sz, b) in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.CENTER
        r = p.add_run()
        r.text = t
        r.font.size = Pt(sz)
        r.font.bold = True if b else None
        r.font.color.rgb = txt_color
    return sh

def arrow(slide, x1, y, x2, dash=False):
    conn = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT,
                                      Inches(x1), Inches(y), Inches(x2), Inches(y))
    conn.line.color.rgb = DK2
    conn.line.width = Pt(2.25)
    ln = conn.line._get_or_add_ln()
    if dash:
        etree.SubElement(ln, f'{{{A}}}prstDash', {'val': 'dash'})
    te = etree.SubElement(ln, f'{{{A}}}tailEnd')
    te.set('type', 'triangle'); te.set('w', 'med'); te.set('len', 'med')
    return conn

def label(slide, x, y, w, text, sz=12, color=DK2, bold=False):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(0.3))
    tf = tb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = text
    r.font.size = Pt(sz)
    r.font.bold = True if bold else None
    r.font.color.rgb = color
    return tb

# ---------- 1. 封面（slide1）：改文字、取消隐藏 ----------
cover = prs.slides[0]
for sh in cover.shapes:
    if not sh.has_text_frame:
        continue
    if sh.name == '文本框 2':
        replace_in_paragraph(sh.text_frame.paragraphs[0], '10月11日组会汇报')
    elif sh.name == '文本框 58':
        ps = sh.text_frame.paragraphs
        replace_in_paragraph(ps[0], '汇  报 人：孙国华')
        replace_in_paragraph(ps[1], '日    期 ：2026年10月11日')
if 'show' in cover._element.attrib:
    del cover._element.attrib['show']

# ---------- 2. 删除原内容页 slide2-8（保留封面与致谢页） ----------
layout = prs.slides[1].slide_layout   # '1_标题幻灯片' 空白版式（master1）
for idx in range(7, 0, -1):
    delete_slide(prs, idx)
# 现在顺序：[封面, 致谢]
# python-pptx 按 len(sldIdLst)+1 命名新页，会与仍存在的致谢页 slide9.xml 撞名
# （产生重复 zip 条目，PowerPoint 会弹修复）。先把致谢页部件改名为 slide99.xml。
from pptx.opc.packuri import PackURI
thanks_slide = prs.slides[1]
thanks_slide.part.partname = PackURI('/ppt/slides/slide99.xml')

def new_slide():
    return prs.slides.add_slide(layout)

# ---------- 3. 页2 本次汇报内容 ----------
s = new_slide()
add_title(s, '本次汇报内容：')
add_body(s, [
    [('主线一　模型上船"趴窝"事故：', True), ('新策略部署到仿真只肯出 4% 的推力——查出是单位搞错了，从导出到部署两头焊死、防止复发', False)],
    [('主线二　给控制系统装"记录仪"和"考官"：', True), ('先如实记下每一步发生了什么，再用两进程架构把"谁来发指令"管起来', False)],
    [('主线三　一次代码安全体检：', True), ('查出四个可能导致"船乱跑、发旧指令"的漏洞，全部修复并在部署机上验证', False)],
    [('主线四　差分定位（RTK）断流修复：', True), ('账号停用＋通信方式不合的双重故障，修好后定位精度从米级提到分米级', False)],
    [('四条主线的关系：', True), ('事故暴露"实验室里对 ≠ 上船后对"——先把事实记全，再把执行管住；安全和定位是上船的两条底线', False)],
    [('数字都有出处：', True), ('v5 修复报告、10-09 部署记录、研究教程与数据契约文档', False)],
], y=1.95, sz=15)

# ---------- 4. 主线一（3 页） ----------
s = new_slide()
add_title(s, 'RL 部署事故闭环修复：')
add_body(s, [
    [('事故现象：', True), ('新策略部署到仿真就"趴窝"——平均速度 0.267 m/s（正常 0.86），最大推力 1.0 N，只占满量程 ±25 N 的 4%', False)],
    [('打个比方：', True), ('模型喊的是"油门 80%"，推进器收到的却是"0.8 牛"——数值全对，单位错了', False)],
    [('直接原因：', True), ('v5 起模型输出改成了 -1～1 的"比例值"，部署代码却仍把它当"牛顿数"直接下发', False)],
    [('根子在导出环节：', True), ('单位换算依赖训练时的配置，训练一改它就悄悄失效——不报错、不停下，留下一个"看起来对"的模型', False)],
    [('雪上加霜的两点：', True), ('缺归一化统计文件时只警告、照常导出；"自检"用模型自己的数据——自己验自己，永远合格', False)],
    [('最迷惑的一点：', True), ('权重、观测、训练曲线全"正确"，它就是不动——这次不是策略钻空子，是管线对部署撒了谎', False)],
])

s = new_slide()
add_title(s, 'RL 部署事故闭环修复：')
add_body(s, [
    [('修复思路：', True), ('靠"约定"会错，就把单位焊进模型里，再让导出、部署两头互相对质', False)],
    [('导出侧：', True), ('把"×25 换算成牛顿"直接写死在模型内部，输出即牛顿；系数只认 25，填别的当场拒绝导出', False)],
    [('配一张"身份证"（manifest）：', True), ('模型哈希、输入输出规格、量程 ±25 N、导出命令全记录——证和模型互相咬合，改一个就露馅', False)],
    [('独立复核：', True), ('换一条完全独立的计算路径复核模型输出，误差 1.9e-5 牛（要求小于千分之一）——对不上就不许发布', False)],
    [('部署侧：', True), ('上电先验"身份证"——文件哈希、规格、量程逐项对质，全部对上才允许推理', False)],
    [('失败即安全：', True), ('任何一项对不上就拒绝启动、推力为零——宁可不动，不能乱动（5 类失败场景均有测试）', False)],
])

s = new_slide()
add_title(s, 'RL 部署事故闭环修复：')
add_plain_table(s, [
    ['指标', '修复前', '修复后', '说明'],
    ['最大推力', '1.0 N', '20.15 N', '满量程 ±25 N'],
    ['平均速度', '0.267 m/s', '0.861 m/s', '提速 3.2 倍'],
    ['最大速度', '0.299 m/s', '1.152 m/s', '—'],
    ['平均横向偏差', '0.117 m', '0.147 m', '速度上来更难贴线（如实标注）'],
    ['独立复核误差', '—', '1.9e-5 N', '要求 < 1e-3 N'],
    ['测试', '—', '74 项全过', '导出 46 ＋ 部署 28'],
], x=0.72, y=1.95, col_in=[2.9, 2.6, 2.9, 3.5], row_h_in=0.5, sz=16, sz_hdr=16)
add_body(s, [
    [('慎读：', True), ('这次证明的是"单位和接口修对了"，不证明"跟得更准了"；仿真 60 秒短程验收', False)],
    [('出处：', True), ('v5_ONNX_物理推力缩放_修复报告_2026-10-03', False)],
], x=0.95, y=5.75, w=11.4, sz=13)

# ---------- 5. 主线二（3 页，含架构图） ----------
s = new_slide()
add_title(s, 'P0/P1 研究安全架构：')
add_body(s, [
    [('干什么：', True), ('给控制系统装"行车记录仪"——每一步"看到什么状态、算了什么题、发了什么指令"全部原样存档', False)],
    [('四路记录：', True), ('船态快照（船在哪、多快）、耗时日志（每步用多久）、指令日志（每次发布成败）、参考记录（求解器实际收到的目标轨迹）', False)],
    [('诚实边界：', True), ('有五件事这份记录证明不了（比如"仿真真的执行指令了吗"），一律如实标"未证明"——宁可少说，不许夸大', False)],
    [('双配置设计：', True), ('控制器脑内的"船模型"和仿真里的"真船"参数故意不同——误差已知、可控，留给后续研究"模型不准时怎么办"', False)],
    [('防篡改：', True), ('录制配置启动时定格、录完复核；检查脚本只读不写，序号断一拍都算不合格', False)],
])

s = new_slide()
add_title(s, 'P0/P1 研究安全架构：')
label(s, 0.95, 1.80, 11.5,
      '两进程分工——一个只管算、一个只管发：计算进程崩了顶多"没人交卷"，绝不会"交一份错的"', sz=15, bold=True)
box(s, 1.1, 2.50, 4.0, 2.5, ACCENT1, [
    ('p1_regulator 监管进程', 16, True),
    ('唯一有权发布指令', 13, True),
    ('200 ms 节拍 · 全链核对后放行', 11, False),
    ('出题 → 收卷 → 判卷', 12, False),
])
box(s, 8.3, 2.50, 4.0, 2.5, DK2, [
    ('p1_solver_worker 计算进程', 16, True),
    ('只管算题、独占求解器', 13, True),
    ('验题 → 求解 → 交卷', 12, False),
    ('迟到的题连算都不算', 12, False),
])
arrow(s, 5.15, 2.95, 8.25)
label(s, 5.15, 2.60, 3.1, '出题：定格快照＋参考　/p1/solve_job', sz=11)
arrow(s, 8.25, 3.75, 5.15)
label(s, 5.15, 3.40, 3.1, '交卷：首拍指令＋预测　/p1/solve_candidate', sz=11)
arrow(s, 8.25, 4.55, 5.15, dash=True)
label(s, 5.15, 4.20, 3.1, '心跳：每 200 ms 一跳　/p1/worker_capability', sz=11)
box(s, 1.1, 5.35, 11.2, 0.62, TINT, [
    ('三级放行：不输出 → 影子跟随 → 真正执行（"真正执行"的开关焊死在代码里，须过专门评审）', 13, True),
], txt_color=DK2)
box(s, 1.1, 6.13, 11.2, 0.62, TINT, [
    ('任一环节出问题 → 兜底：保持上一指令 600 ms，再按 80 N/s 平缓衰减到零', 13, True),
], txt_color=DK2)

s = new_slide()
add_title(s, 'P0/P1 研究安全架构：')
add_body(s, [
    [('迟到不收：', True), ('超过截止时间的解一概不用——迟到的答案基于旧状态；过点后连题都不让它算，五道关卡层层拒收', False)],
    [('出题定格：', True), ('出题瞬间把状态、参考、历史"拍照"成一份冻结快照，中途世界怎么变都不影响这道题', False)],
    [('判卷对质：', True), ('放行前核对"从答题到打分之间条件没被偷偷改过"——每次数据发布的序号必须连续、数值未变', False)],
    [('双保险看活：', True), ('200 ms 心跳＋600 ms 收据超时＋pidfd 查"户口"——计算进程真死了立刻发现，进程号被复用也骗不过', False)],
    [('规模与验证：', True), ('8 种消息、7 组测试约 80 个用例；另有 250/400 ms 人为卡顿的实战录包验证', False)],
    [('一句话总结：', True), ('所有机制防的都是同一类事故——"基于旧世界的新指令"；宁可走兜底，不发错指令', False)],
])

# ---------- 6. 主线三（2 页） ----------
s = new_slide()
add_title(s, '代码安全审查修复：')
add_plain_table(s, [
    ['编号', '问题', '后果', '修复'],
    ['C1', '刚检查完"有路径"，开算前路径被清空', '船径直驶向地图原点', '把检查搬进锁内'],
    ['C2', '关机流程与正在算的求解撞车', '未定义行为', '关机标志＋互斥锁'],
    ['M1', '全零四元数被当成"航向 0°"', '航向最多错 180°', '范数门禁丢弃'],
    ['M2', '只看求解器自己的计时', '卡顿时发布过期解', '墙钟＋内部双计时'],
], x=0.72, y=1.95, col_in=[0.9, 4.4, 3.1, 3.5], row_h_in=0.62, sz=14, sz_hdr=16)
add_body(s, [
    [('C3 顺手修复：', True), ('原来 MPC 崩了只打日志，而飞控会"记住"最后一条速度指令——船停不下来；现改为请求悬停', False)],
    [('为什么这么修：', True), ('A/B 两套 MPC 代码八成重复且已分叉——四项全部搬运"已验证的 B 版实现"，不另起炉灶', False)],
], x=0.95, y=5.35, w=11.4, sz=14)

s = new_slide()
add_title(s, '代码安全审查修复：')
add_body(s, [
    [('本地验证：', True), ('测试全绿——kinematic 8＋13、bringup 5、simulation 9、RL 单元 28 项；另新增 8 个超时用例', False)],
    [('部署机回归：', True), ('树莓派上 8 项全过，含真实日志"全零四元数，已丢弃"；机上源码与本地只差 38 个大括号（纯格式）', False)],
    [('部署后状态：', True), ('6 个控制节点＋差分＋中继在线；MPC 待命无故障；差分数据 6.8 Hz；定位 RTK Float', False)],
    [('顺手修复：', True), ('RL 节点加异常保护＋NaN 三道闸（防一次异常打崩整个节点）；可视化"轨迹冻结"bug（跑几分钟后轨迹不再刷新）', False)],
    [('已知缺口：', True), ('kinematic 的待命路径没清指令缓存——停很久后万一超时会重放旧速度（另一套已修，这边没跟齐）', False)],
    [('待办清单：', True), ('CMake 顺序、头文件重名、模式管理器新鲜度、前馈单位错等 8 项', False)],
])

# ---------- 7. 主线四（2 页） ----------
s = new_slide()
add_title(s, 'RTK NTRIP 链路修复：')
add_body(s, [
    [('背景一句话：', True), ('RTK＝岸上基准站发"改正数"，把 GPS 从米级提到分米级——前提是两边先"对上话"', False)],
    [('两个叠加故障：', True), ('① 服务账号被停（401 报错），客户端退出后无人拉起；② 换新账号后又发现两边"投递方式"不合（一边要求必达、一边随缘），位置报告被静默丢弃，基准站不知道我们在哪、不发改正数', False)],
    [('修复：', True), ('加一个 38 行的"翻译中继"节点把两边接通，差分客户端改读中继话题', False)],
], y=1.88, sz=15)
add_plain_table(s, [
    ['指标', '修复前', '修复后'],
    ['差分数据注入 /send_rtcm', '无（账号 401）', '约 5 Hz（30 秒 164 条）'],
    ['定位类型 fix_type', '3 单点，误差约 3.2 m', '5 RTK Float，分米级'],
    ['飞控收到改正数', '—', '抓包确认（msgid 233）'],
], x=0.72, y=4.15, col_in=[3.9, 3.9, 4.1], row_h_in=0.52, sz=16, sz_hdr=16)

s = new_slide()
add_title(s, 'RTK NTRIP 链路修复：')
add_body(s, [
    [('现状：', True), ('差分链路全通，定位达到 RTK Float（分米级）；重启后 1–2 分钟即可恢复', False)],
    [('遗留一：', True), ('Float 与单点之间波动，还没到最高的 Fixed 档——多路径/遮挡＋只有 11 颗星', False)],
    [('遗留二：', True), ('差分账号 10-10 到期，需续费；若未处理，当前已失效', False)],
    [('遗留三：', True), ('中继与差分客户端都不会自动重启——两个"单点"，再出同款故障仍要人到场', False)],
    [('配套沉淀：', True), ('录制清单补两个 GPS 质量话题；树莓派↔飞控数据流文档固化（串口命名、白名单未生效、IMU 仅 1 Hz 待调）', False)],
])

# ---------- 8. 后续工作（模板 slide8 极简风格） ----------
s = new_slide()
add_title(s, '后续工作：')
add_body(s, [
    [('1、补齐 kinematic 待命清缓存的缺口', False)],
    [('2、攻克 RTK Fixed 与差分账号续期', False)],
    [('3、P1 从"影子"走向"真正执行"（过专门评审）', False)],
    [('4、仓库卫生：忽略规则、冻结清单补全', False)],
], x=1.13, y=2.19, w=11.0, h=1.6, sz=20, spc_after=800)

# ---------- 9. 致谢页移到末尾 ----------
lst = prs.slides._sldIdLst
ids = list(lst)
thanks = ids[1]
lst.remove(thanks)
lst.append(thanks)

prs.core_properties.title = '10月11日组会汇报'
prs.save(OUT)
print(f'saved: {OUT}, slides={len(prs.slides)}')

# ---------- 10. 程序化 QA：重开 + 溢出估算 ----------
prs2 = Presentation(OUT)
print(f'reopen OK, slides={len(prs2.slides)}')
issues = []
for si, sl in enumerate(prs2.slides, 1):
    for sh in sl.shapes:
        if not sh.has_text_frame:
            continue
        w_in = (sh.width or 0) / 914400
        top = (sh.top or 0) / 914400
        est_h = 0.0
        for p in sh.text_frame.paragraphs:
            txt = ''.join(r.text for r in p.runs)
            if not txt:
                continue
            sz = max((r.font.size.pt if r.font.size else 14) for r in p.runs)
            cpl = max(1, (w_in - 0.2) / (sz / 72.0))
            est_h += math.ceil(len(txt) / cpl) * (sz / 72.0) * 1.3 + 0.06
        if top + est_h > 7.35:
            issues.append(f'slide{si} {sh.name}: est_bottom={top + est_h:.2f}in')
print('overflow suspects:', issues if issues else 'none')
