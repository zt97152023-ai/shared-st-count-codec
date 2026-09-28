# Production Shared 源码交付

**2026-09-28 修订：** [冻结运行映射、比较器契约及 E3 更正](provenance/REPRODUCIBILITY_CONTRACT.md)。补入遗漏的 E3 worker 与逐例证据；历史运行 commit 未记录，不能将发布 commit 当作运行 commit，也不宣称完整软件复现链闭合。

这是原项目源码的逐字节归档，不是重写实现。SOURCE_MANIFEST.json记录原位置、文件大小与SHA256；HISTORICAL_PIN_CHECKS.json核对历史固定哈希。

## 先选版本

|版本|真实入口|用途|
|---|---|---|
|历史Shared，support B8/value K8|baseline/matched_ready|早期结果；默认不是K32|
|容量扩展Shared，B8/K8|baseline/hest_large_runtime|500M逻辑元素上限，概率规则保持历史实现|
|千例主结果，B8/K32|baseline/evidence/COUNT-HEST-SHARED-K32-001/worker.py，显式 --K 32|推荐用于对应千例论文结果|
|后续support/context消融|baseline/evidence/COUNT-SUPPORT-PREDECESSOR-50-001、COUNT-PRODUCTION-SHARED-ABLATIONS-50-001、COUNT-PRODUCTION-SHARED-CLOSURE-001|研究代码；不得替换千例默认配置或当成重新评价结果|

K32不是把核心model.py里的一个8直接改成32。历史worker动态构造value模型、header和decoder，support仍为8。必须保存并使用worker与它所依赖的全部源码。普通matched_ready解码入口不等价于K32入口。

## 环境与单文件使用

Python 3.11环境；依赖numpy、scipy、h5py、numba。requirements-tested.txt是本次源码副本小测试的已安装版本，不冒充所有历史实验的统一环境。没有公共神经checkpoint需要下载。所有数据特定概率参数应从archive读取。

在本包根目录执行，下列输出路径必须是未使用的新位置：

```text
python -B -X utf8 baseline/evidence/COUNT-HEST-SHARED-K32-001/worker.py encode INPUT.h5ad OUTPUT.cnt --K 32 --report encode.json
python -B -X utf8 baseline/evidence/COUNT-HEST-SHARED-K32-001/worker.py decode OUTPUT.cnt DECODED_DIRECTORY --report decode.json
python -B -X utf8 baseline/evidence/COUNT-HEST-SHARED-K32-001/worker.py verify INPUT.h5ad DECODED_DIRECTORY --report verify.json
```

第二条命令只输入archive；第三条是对照原输入的验证。decode根据manifest识别value K。encode不指定--K时历史worker默认8，**不能省略--K 32**。不要传--shuffle，该选项只用于消融。

恢复合同是规范化整数count、轴标签及顺序、坐标和规定metadata；不是完整H5AD文件布局或所有附加字段。输入浮点数仅在值为合法整数时可转为canonical int64。输入gene顺序和spot顺序保持，图写入归档；不凭空给单细胞构造生物空间。

## 源码验证

本次233个原始文件复制后SHA一致；39个历史pin全部匹配。源码副本在原有Python环境执行K8/K32微型合成数据真实编码、分别新进程archive-only解码、精确恢复；覆盖零行、零gene、重复gene标签和uint32尾部值。记录见包内validation。

这是源码依赖与基本可运行性检查，不是千例重新复现，不证明任意平台安装均可运行。未打包Python解释器、pip包或第三方native二进制；S0/pcodec以及非Shared比较器可能另需依赖，不在本次Shared小测试范围。

## 阅读顺序

1. SOURCE_MAP.md：方法模块与代码对应。
2. baseline/evidence/COUNT-HEST-SHARED-K32-001/README.md、PROTOCOL.json：实验配置与范围。
3. worker.py → hest_large_runtime/shared.py → sharedcodec/model.py、qpatchcodec/model.py、qshare_model.py、values.py。
4. hest_large_runtime/decoder.py、archive.py：独立解码与六类物理账本。

研究目录包含历史run.py/setup.py等批处理脚本，其中有原始磁盘和运行配置。它们用于追溯，不是本包默认启动命令；不应直接运行整个历史千例批处理。旧工程文档若描述历史状态，以本说明的版本区分为准。
