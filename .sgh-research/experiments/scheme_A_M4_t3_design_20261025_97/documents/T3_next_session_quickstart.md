# 下一会话快速启动指南

日期:2026-10-25。基于第70-96批完整执行经验编写。

## 立即可用的基础设施

### 冻结+执行(批90模式)
```bash
# 1. 新建批次目录
B=/path/to/new_batch
mkdir -p $B/implementation $B/evidence $B/postrun $B/documents

# 2. 复制树和基础设施(从批91)
cp -r /path/to/batch91/implementation/t2_author $B/implementation/
cp /path/to/batch91/implementation/setup_env.sh $B/implementation/

# 3. 用Write工具写freeze.py(参考批90的freeze.py)
# 关键: ROOT-relative paths, setup_env.sh引用, 不要用shell heredoc写Python

# 4. 执行
cd $B
python3 implementation/freeze.py  # 构建ELF+registry+registration
/bin/bash implementation/setup_env.sh \
  /usr/bin/python3 -B \
  $(realpath implementation/t2_author/t2_scenario_driver_v1.py) \
  --registration $(realpath implementation/T2C_registration.json)
```

### 审计
```python
import sys; sys.path.insert(0, 'path/to/t2_author')
import audit_t2, json
table = json.loads(open('table.json').read())
result = audit_t2.audit_run('path/to/run_dir', table)
print(result['passed'], result['checks'], result['failures'])
```

## 立即任务(优先级排序)

### 1. T2-B新代际正控(设计批)
- **问题**: 已建立Epoch在path变更后变为terminal;同run内无法恢复新代际
- **需要**: scoped Epoch生命周期设计(允许同run内Epoch重置或新创建)
- **禁止**: 简单改101→201或换run_id(82批R74-07)
- **参考**: `task_time_profile_v1.hpp` 的 Epoch class; `regulator_owned_execute.cpp` 的 reference_epoch_ 成员

### 2. T3 Source队列压力/cleanup
- **目标**: cleanup_failed路径测试 + 旧group未空禁止restart + Source队列压力
- **入口**: Sink类(`regulator_owned_execute.cpp` L66区)的queue/buffer/overflow
- **方法**: 组件级测试(类似批70的harness),不需完整owned run

### 3. N3/M4差集复判
- **前置**: T2差集闭合(或明确声明遗留)
- **内容**: 原九组联合复判;组件/阶段资格/研究结论分别判定

### 4. F6→P1
- **前置**: N3/M4复判通过

## 已通过运行的证据位置

| 运行 | 路径 |
|---|---|
| T2-B replace | batch81/implementation/runs/T2B_P01 |
| T2-B clear | batch91/implementation/runs/T2B_CLR |
| T2-B expired | batch91/implementation/runs/T2B_EXP |
| T2-C | batch91/implementation/runs/T2C_OPTA |
| T2-A silent | batch91/implementation/runs/T2A_G5 |
| T2-A same_stamp | batch91/implementation/runs/T2A_SS |
| T2-A resume NW | batch91/implementation/runs/T2A_RNW |

## 常见问题与解决方案

| 问题 | 解决 |
|---|---|
| Driver tool SHA mismatch | 重运行freeze.py(重建ELF);或更新registry driver SHA |
| Output directory exists | 删除旧run目录或改registration output路径 |
| Shell引号问题 | 用Write工具直接写Python;不用heredoc |
| setup_env.sh环境变量 | 确保DDS vars在exec "$@"之前 |
| 相对路径argv mismatch | 始终用$(realpath ...)获取绝对路径 |

## 资格状态(不变)

M4/F6/P1/plant/硬实时全部false;生产B仍MANUAL+RC覆写。
