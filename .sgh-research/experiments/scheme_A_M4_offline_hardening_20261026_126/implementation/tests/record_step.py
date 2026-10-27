"""Record functional step evidence without erasing historical process failures."""
from pathlib import Path
import json
from offline_support import ROOT, QUALIFICATION, save


def record_step(step, evidence, description, changes, remaining=()):
    evidence = Path(evidence).resolve()
    result = json.loads((evidence / 'verification.json').read_text())
    assert result['status'] == 'PASS' and not result['failures']
    versions = sorted((ROOT / 'postrun').glob(step + '_step_result*.json'))
    name = step + ('_step_result.json' if not versions else f'_step_result_v{len(versions)+1}.json')
    target = ROOT / 'postrun' / name
    save(target, {'step_id': step, 'status': 'PASS', 'scope': 'functional offline checks only',
                 'description': description, 'evidence': str(evidence),
                 'observed_facts': result['observed_facts'], 'run_accepted': result['run_accepted'],
                 'coverage': {'checks': result.get('checks'), 'verification_schema': result.get('schema'),
                              'verification_reference': str(evidence / 'verification.json'),
                              'owned_runtime': 'not_covered'},
                 'changed_files': changes, 'remaining_obligations': list(remaining),
                 'qualification': QUALIFICATION, 'stage_qualified': False,
                 'batch_process_conformance': False,
                 'process_note': 'E04 pre-takeover attempt wrote then restored a protected original. It remains a historical FAIL_STOP process finding; component PASS does not waive it.'})
    status_path = ROOT / 'postrun/step_status_v1.json'
    status = json.loads(status_path.read_text())
    status['steps'][step]['status'] = 'PASS'
    status['steps'][step]['latest_result'] = str(target.relative_to(ROOT))
    attempts = status['steps'][step]['attempts']
    if evidence.name not in attempts:
        attempts.append(evidence.name)
    status['historical_process_status'] = 'FAIL_STOP'
    status['historical_process_finding'] = 'E04 original transient write, restored; retained, not waived'
    status['current_authority'] = 'User requested takeover and continued modifications; functional steps retain their order. This does not retroactively certify original preservation.'
    status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2) + '\n')
    rows = ['# 第126批：离线整改执行与接替记录\n',
            '依据第125批计划继续修改。表中PASS只描述具名离线功能验收；阶段资格全false。\n',
            '| 步骤 | 功能状态 | 最新回执 |', '|---|---|---|']
    for sid, entry in status['steps'].items():
        rows.append(f"| {sid} | {entry['status']} | {entry.get('latest_result', 'postrun/'+sid+'_step_result.json' if entry['status']=='PASS' else '—')} |")
    rows += ['\n## 必须保留的过程失败\n',
             'E04接替前attempt01曾修改B103封存CMakeLists.txt并恢复，旧回执已记录；不能将当前SHA相等写成“全程零写入”。全批过程符合性仍为FAIL_STOP，E12不得无条件给OFFLINE_HARDENING_ACCEPTED。\n',
             '本轮接替快照与身份记录：`evidence/E05/attempt04/takeover_manifest.json`。旧失败、旧PASS与旧CURRENT保留；E05因实际接口绕过重新验收。\n',
             '生产树、既有未提交文件与旧run保持；实船B为MANUAL+RC覆写。当前只执行离线功能整改，未初始化ROS、未运行owned。\n']
    (ROOT / 'CURRENT.md').write_text('\n'.join(rows) + '\n')
