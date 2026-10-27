# 77—81冻结记录可重验性补核

本次仅比较文件存在性与SHA256，未恢复、覆盖历史资产，也不推断修改主体或意图。完整清单为`identity_history_v1.json`，简表为`identity_history_summary_v1.json`。有界搜索为77—81批679项非build普通文件，另检查当前registry登记的四个ELF；不能由本次未命中推断全盘绝无备份。

## 78 freeze_rev11报告与当前文件

- 报告固定bundle`51ca3d42425ed4275adefcc87bf79d8fb91e3300aff150f038466a4c237e5422`，同路径当前为`d588fa4859096c38e266d64ef6017342320de473b62bb9d36043d97d06c09acb`。
- 报告Driver`935cd6b8f7d2faa290c920210b0be32e6476719f8ef733da11fe44b927716818`，当前为`f5556b043bd374d87ee7fdcc732d2c2c498ac0c887120de936471b086301baaf`。
- 报告Worker/Regulator/Fixture ELF都与同路径当前字节不符；复用Recorder匹配。
- 当前registry与P01 manifest一致，当前四ELF/Driver均匹配；bundle103项中102项在其登记的78/r3路径匹配，唯一audit_t2.py不匹配。
- 77是未生成正式freeze/registry的离线scope派生，不将其source派生目录冒充正式owned来源。

## 79旧run逐项结果

78/runs下的B01、B03至B11共有10个留存Driver manifest。每个manifest的完整registration/registry/Driver/role ELF/bundle SHA已逐条写JSON。

- 所有10个旧run的registrySHA都与当前registry不同；有界搜索未找到对应精确registry JSON。
- B01/B03/B04/B05/B06/B07/B08/B09/B10的Driver SHA与当前不同。
- B11 Driver与当前匹配；其精确副本也在80/r4。
- B11 registration当前精确原件仍在79/implementation/T2B_boundary_registration.json，SHA为`323a2ad7c6b7fb0beccd9e913d35495655a07fcd7a8d5b0583456ed4a61542e4`；但它指向的registry SHA5b145f38与当前7005ddb4不符。
- 其余9个旧run的registration SHA在有界registration文件清单中未找到精确原件。
- 旧run已经生成的Fixture/Worker/Regulator manifest，其ELF pin和bundle pin全部与当前对应物不符；已生成的Recorder manifest仍匹配复用Recorder。
- 简表中的null只表示该run未留存相应角色manifest，不能据此推断角色从未spawn。

## 81 P01

- registration精确文件存在，registry SHA7005ddb4、Driver f5556b04、四ELF和manifest声明的bundle SHA均与当前registry一致。
- 但当前bundle记录的audit原件SHA72644f6a与78/r3实际170bf747不符，因此“当前全部冻结链可复验”仍为false。

## 80/r4可保留的精确来源

80/r4的**全部103个相对源文件**，逐个SHA都匹配P01 source_bundle记录。故它保存了一组可独立回读的精确登记源文件人口；这不等于它已有独立registry/ELF来源资格。

尤其：

- `audit_t2.py`是精确登记原件`72644f6a…`；
- Driver是P01与B11共同声明的`f5556b04…`；
- `worker/solver_worker_m4.cpp`、t2_action_contract.py、w2_runtime_contract.py、common/m4_owned_runtime.hpp等均逐字节匹配P01 bundle记录。

未在该有界清单找到B11旧bundle完整JSON或其三个旧ELF精确副本；不能用80/r4源文件人口替代旧ELF或旧bundle JSON的SHA证明。
