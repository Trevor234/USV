"""E10: append corrections to the one register; retain the complete preimage."""
from pathlib import Path
import difflib
import json
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'implementation/tests'))
from offline_support import Evidence, pin, save
e = Evidence('E10', ROOT / 'evidence/E10/attempt01')
reg = ROOT.parents[1] / 'research-innovations.md'
before = reg.read_bytes()
(e.out / 'research-innovations_before.md').write_bytes(before)
before_pin = pin(reg)
source = {
    'Epoch': ROOT / 'implementation/author/observer/src/shadow/scoped_epoch_v1.hpp',
    'Regulator': ROOT / 'implementation/author/observer/src/shadow/regulator_owned_execute.cpp',
    'B2': ROOT / 'implementation/author/fixture/resume_stamp_mapping_v1.hpp',
    'model': ROOT / 'implementation/standalone/model/model_transaction_v1.hpp',
    'RNW': ROOT / 'implementation/audit/rnw_audit_v3.py',
    'CDR': ROOT / 'implementation/audit/stored_control_reader_v1.py',
    'Q2': ROOT / 'implementation/tests/test_t3_queue_pressure_v2.cpp',
}
items = [
 ('I-2026-10-25-01', 'scoped Epoch代际生命周期',
  '撤回混入本条的p_global模型事务与“不开任何复活通道”的普遍承诺。Epoch的绑定生命周期与模型capsule事务是两个机制。124已证实旧Proposal可误提交、ledger测试不独立。126补入实例/代际/serial/预期binding认证、wrapper侧消费状态，移除公开raw commit并接到真实Regulator的既有临界区；15个组件case、4个定向变异及实际Regulator编译通过。原6 case的32条断言保留。新token接线没有新owned运行证据，104/119旧正例不能替代它。', ['Epoch','Regulator'], 'Epoch'),
 ('I-2026-10-25-02', 'B2恢复stamp配对映射',
  '“结构性消除投影回退”改为有限条件下的实际发布配对映射。126检查int64加减、显式cap和错误结果，并在Fixture发布前检查正常域与ROS时间范围；算术cap仍为4.9s，5s阈值不变。原16项算术正控保留；11项边界/限制case及2个实际helper变异通过。4ms接收错相回退和1.1s长hold回退仍成立；不能保证任意DDS时延或长hold下的正常恢复。', ['B2'], 'B2'),
 ('I-2026-10-25-03', '有限p_global模型事务',
  '“逐位等价/天然原子”改为固定M0/M1、固定输入、单所有者串行调用下，u和前6维X在1e-8内的有限数值对拍；观测差值0.0不推出任意输入逐位等价。126补UNCOMMITTED/READY/PREPARED/FAULTED、非零代际、有限值/形状检查、setter/reset结果与所有者检查。19个case和3个变异通过；链接层观察真实C solve入口。失败adapter只证明包装层状态策略，未证明生成setter内部错误传播。比较对象是此次钉住的安装库，不是当前dirty生产源码。完整mixed身份、真实tick激活、生产fallback和warm失败路径仍待集成。', ['model'], 'Model'),
 ('I-2026-10-25-04', '有限survivor与cleanup失败事实',
  'SIGTERM handler只设置stop，fork发生在main退出循环后的关闭路径。实现只关闭fd3—255，未处理fork失败；3s是用户态自退出目标，不能写成内核绝对硬界。C12的父rc0/组非空/cleanup_failed与C3的组空按原始Driver日志复判保留；此次无新信号、无survivor运行，不认证通用清理器。', [], 'History'),
 ('I-2026-10-26-05', '同Job链审计',
  '“按流序绑定”改为按完整身份及逻辑时刻绑定。126发现早期修订仍遗漏Worker/Stored，随后补齐四类完整类型：Job44、Candidate14、Decision57、Applied39字段；实际Job7/seq18、真实C调用1次及四类全人口对账通过，缺证据/错echo/错右通道/错时序等负例被拒。Source typed-CDR摘要与Stored原始CDR不等，未声称全字节等价；完整字段按类型支持和冻结emitter复算。无旧在途仍为not_covered，不能充作拒绝证据。完整run接受是本RNW家族的有限结论，不是M4/P1资格。', ['RNW','CDR'], 'RNW'),
 ('I-2026-10-25-06', 'Q1d确定性压力与Q2身份修复',
  'Q1d受控阻塞下capacity+1性质保留，不能外推为Q2身份正确。旧Q2保留350/303重复身份反例；126按值捕获base，逐producer及局部序号做offered/accepted/rejected分区、发布与落盘多重集对账。5个case、ASAN/LSAN和实际引用捕获变异通过；ptrace中的LSAN工具失败原件保留，未关闭sanitizer换取通过。', ['Q2'], 'Q'),
]
marker = '## 2026-10-26 第126批审核性修订'
assert marker.encode() not in before
text = '\n\n' + marker + '\n\n以下修订替代前文同ID的**当前性质与复用范围**；前文保留为历史，不再作为现行验收结论。已证工程事实不自动构成学术新颖性。\n'
for iid, title, body, names, family in items:
    text += '\n### ' + iid + ' 当前认定：' + title + '\n\n' + body + '\n\n'
    for name in names:
        path = source[name]
        text += f'- 源：`{path}`，SHA256 `{pin(path)["sha256"]}`。\n'
    text += f'- 本轮证据：`{ROOT / "evidence/E09/attempt02" / family}`。\n'
text += '\nD-2026-10-26-01仍未实施/未证明；D-2026-10-26-02仍未写作。M4/F6/P1/plant/硬实时全false，生产B维持MANUAL+RC覆写。\n'
text += '\n过程符合性单列：126的E04接替前发生封存文件误写并恢复，保留为历史FAIL_STOP；当前hash一致不能改写该事实，功能回归通过不等于125执行合同全部签收。\n'
save(e.out / 'registration.json', {'register': str(reg), 'before': before_pin,
     'ids': [x[0] for x in items], 'append_only': True, 'academic_novelty_checked': False})
assert pin(reg) == before_pin
with reg.open('ab') as stream:
    stream.write(text.encode())
after = reg.read_bytes()
e.check('single_register_append_only', after[:len(before)] == before and len(after) > len(before))
e.check('all_six_current_scopes_present', all(('### ' + x[0] + ' 当前认定').encode() in after for x in items))
e.check('all_current_source_pointers_exist', all(p.is_file() for p in source.values()))
(e.out / 'register_append.diff').write_text(''.join(difflib.unified_diff(before.decode().splitlines(True), after.decode().splitlines(True), fromfile=str(reg)+' before', tofile=str(reg)+' after')))
save(e.out / 'register_identity.json', {'path': str(reg), 'before': before_pin, 'after': pin(reg),
     'source_pins': {str(p): pin(p) for p in source.values()}, 'academic_novelty_checked': False})
result = e.finish(register_before=before_pin, register_after=pin(reg), appended_entries=6, academic_novelty_checked=False)
assert result['status'] == 'PASS'
