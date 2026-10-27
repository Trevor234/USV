# T2-B Boundary Root Cause

## 问题
boundary_entered→release ≈ 200ms,超出150ms Job deadline,导致boundary总是"expired"。

## 根因
Worker的`source.jsonl`使用C++ ofstream缓冲写入。`w2_boundary_entered`事件写入后停留在流缓冲区,直到下一轮capability消息(~200ms周期)填满缓冲区才flush到磁盘。Driver的SourceCursor读取文件时看不到未flush的数据。

## 证据
- T2B_B09/B10/B11一致:boundary→release ≈ 167-202ms
- boundary_entered在Worker侧的写入时刻 vs Driver侧的观察时刻差 ≈ 200ms
- 不是Driver慢(观察循环无sleep);是数据不可见

## 修复
在Worker的`event()`函数中,对`w2_boundary_entered`类型添加`file_.flush()`。需修改Worker源码+重派生+重冻结。
