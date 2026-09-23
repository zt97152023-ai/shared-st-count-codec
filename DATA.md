# 数据集总结

更新：2026-09-08。**以 HEST 本地数据为来源，047 固定 100 样本为描述性实验面板，INT7 为单独开发样本。** 原始文件不复制、不删除、不移动。

## 1. 数据范围与用途

|层级|数量|用途与边界|
|---|---:|---|
|本地 HEST 元数据条目及 count 文件|1,108|资产清单；未逐一核实全部矩阵内容与使用历史|
|047 固定面板|100|已暴露的描述性比较，9 个配置共 900 项运行状态|
|INT7|1|已暴露开发样本，不在上述 100 个样本中；051 六项结果另组比较|
|其余本地样本|1,007|使用历史尚未审核，不能直接称为未见测试集|

这里的样本数不是患者数。矩阵行可能是 spot、cell 或 bin，取决于平台和处理方式；压缩产物、解码副本、patch 都不能计为额外独立样本。

## 2. 文件位置与规模

|对象|目录|文件数|逻辑文件大小合计|
|---|---|---:|---:|
|表达数据 H5AD|[st](E:/Hestdata/st)|1,108|62.207 GiB|
|局部图像 patch H5|[patches](E:/Hestdata/patches)|1,108|295.175 GiB|
|全幅组织图像 TIFF|[wsis](E:/Hestdata/wsis)|1,108|672.072 GiB|
|样本元数据 JSON|[metadata](E:/Hestdata/metadata)|1,108|约 1.29 MiB|

总元数据：[HEST_v1_0_0.csv](E:/Hestdata/HEST_v1_0_0.csv)。GiB=2³⁰ bytes。上表是这四个目录的文件逻辑长度，不是整个磁盘占用。H5AD 含辅助信息，不能把文件大小当纯 count 大小；patch 与 WSI 是同一组织的不同视图，不是独立样本。

## 3. 平台与生物学构成

平台来自元数据 `st_technology`，不从 INT/MEND/NCBI/TENX 编号前缀猜测。

|平台标签|全部本地条目|047 面板|
|---|---:|---:|
|Visium|515|50|
|Spatial Transcriptomics|552|48|
|Xenium|38|2|
|Visium HD|3|0|
|合计|1,108|100|

`Spatial Transcriptomics` 按原标签保留，未进一步逐研究确认实验版本。047 没有 Visium HD，Xenium 也仅两例，不能据此主张广泛跨平台泛化。

|物种|全部本地条目|047 面板|
|---|---:|---:|
|Homo sapiens|535|50|
|Mus musculus|573|50|

047 共 15 个组织标签：脊髓 30、脑 18、乳腺 8；淋巴结、心脏、皮肤、肾各 6；前列腺、肠各 5；肝、子宫各 3；眼、肌肉、膀胱、骨各 1。组织分布明显不均衡。

疾病状态原标签：Diseased 43、Cancer 30、Healthy 20、Treated 5、Genetically modified 2；它们不是统一的临床分期。

## 4. 当前 100 样本的 count 特征

数值来自 047 冻结源画像；本地来源一致性核验见下一节及逐样本清单。

|指标|统计|
|---|---|
|矩阵行数合计|169,329|
|单样本行数：最小 / 中位 / 最大|60 / 543.5 / 10,878|
|单样本基因数：最小 / 中位 / 最大|541 / 18,474.5 / 55,414|
|非零项总数|577,930,602|
|单样本 nnz：最小 / 中位 / 最大|84,697 / 1,044,013.5 / 77,202,671|
|单样本非零密度：最小 / 中位 / 最大|1.409% / 10.567% / 47.014%|
|按所有矩阵元素加权的非零密度|13.557%，零比例约 86.443%|
|所有样本最大 count|49,490|
|各样本正值中 count=1 的比例，中位数|64.582%|
|各样本正值中 count≤3 的比例，中位数|89.803%|
|100 个源 H5AD 合计|7,054,924,759 bytes，约 6.570 GiB|

中位数可能为半整数。不同样本基因集合不同，不能直接合并成统一列数矩阵；基因数合计也不是唯一基因数。大量小整数值得研究整数编码，但不能截断成 uint8。

## 5. 核验与缺口

|本轮核验项|结果|
|---|---|
|1,108 条目在 st/patches/wsis/metadata 的同名文件集合|全部匹配，无缺失或额外 ID|
|047 本地源 H5AD SHA-256 对比历史源 SHA-256|100/100 一致；矩阵 shape 也全部一致|
|101 样本的表达轴长度与二维有限坐标|101/101 通过头部/坐标检查|
|patch 条码与 count 行完整同序匹配|47/101|
|其余 patch 配对|54 个为 count 条码的有序子集；合计缺少 15,880 行对应 patch，没有额外条码|
|重复表达行标签|0 个样本|
|重复基因轴标签|30 个样本，逐样本明细见核验记录|
|X 的存储 dtype|int64 49、float32 48、float64 2、uint16 2（合计101）|

**直接影响后续使用：** count-only 压缩不因缺 patch 而删除矩阵行；若以后做图像实验，按条码关联并明确缺失处理，不能按相同行号直接拼接。重复基因标签保留列位置和原身份，不能擅自按名称合并；浮点存储也不等于已经归一化，数值整数性与来源需分别判断。

本轮输出 [summary.json](E:/count压缩/evidence/dataset_summary_20260908/summary.json) 与 [101 样本核验记录](E:/count压缩/evidence/dataset_summary_20260908/exposed_samples.json)，检查文件集合、H5AD 轴长度、坐标形状/有限性、patch 条码和本地 H5AD SHA-256。047 本地 hash 与远端运行时源 hash 逐项比较；INT7 单列本地 hash。

额外条码检查：[patch_audit.json](E:/count压缩/evidence/dataset_summary_20260908/patch_audit.json)。可重建脚本：[summarize_datasets.py](E:/count压缩/baseline/reports/summarize_datasets.py)，使用本地 Python 的 h5py/numpy，仅对上述已暴露样本读取头部/坐标/条码及计算源 hash；未重跑 codec 或扫描全部 count 数值。

同名文件只是候选配对；条码匹配支持 count 行到 patch 的关联；有限坐标不证明视觉配准准确。本轮不读取 WSI 像素，不把文件名/条码核对称为图像配准验证。未读取其余 1,007 个矩阵内容。

**供体分组仍需整理：** 047 中 77 个样本缺 patient 字段、12 个缺 study_link。非空 Patient 1 等标签也可能跨研究重复，需研究/来源与供体身份联合核对。

raw count 的实验含义需要处理链支持，不能只看 dtype 或层名。H5AD 含 log1p/QC 辅助列并不自动意味着 X 已做 log 转换；本轮 count 分布复用可追溯的历史画像，不另把分析层当原始矩阵。

元数据许可原文保留在机器清单中，不把全库视为同一许可。当前只作本地整理，不发布原数据。

## 6. INT7 单独使用

[INT7.h5ad](E:/Hestdata/st/INT7.h5ad) 的元数据为 Visium、人、淋巴结。历史 051 使用 2,374×36,601 的完整矩阵，nnz=10,649,786。

它已用于方法开发，适合调试，不作为新盲测。051 与 047 的容器/实验分组不同，不能混合排名。

## 7. 后续实验使用顺序

2026-09-08后续更新：用户明确要求扩到原100例，已执行COUNT-E1-100全部800组合。首次796成功，单次复测补齐4项；独立第二次运行797成功、3项运行异常，完整复现验收未通过。见[100样本报告](E:/count压缩/baseline/EXPERIMENT_RESULT_100.md)。仍未读取其余1007个矩阵。

1. 100 样本用于描述性画像，保留全部方法反例。
2. 首轮按平台内历史密度下中位选定 SPA108、NCBI807、TENX132，完成24组无损实验及独立复现。选择依据与hash见[冻结配置](E:/count压缩/baseline/configs/COUNT-E1-001.json)。空间门槛未过，不自动扩到12例。
3. 按平台与组织分组报告，同来源多片不视为独立供体。
4. 其余 1,007 个样本先查使用历史和供体重复，再确定验证角色。

阅读入口：[101 样本表](E:/count压缩/evidence/dataset_summary_20260908/SAMPLES.md)、[1,108 条目机器清单](E:/count压缩/evidence/dataset_summary_20260908/inventory.json)、[实验计划](E:/count压缩/baseline/EXPERIMENT_PLAN.md)。

历史追溯：[固定面板配置](E:/count压缩/baseline/evidence/panel047_config.json)、[比较结果](E:/count压缩/baseline/results/current/COMPARISON.md)、[旧 DATA_REGISTRY](E:/count压缩/evidence/DATA_REGISTRY.json)。旧登记表保留为历史定位快照，当前信息以本页和新核验清单为准。完整旧实验位于 F:/STCompressBench_CONTINUATION；远端047为 /data2/zhangtian/STCompressBench_E0/panel047/main_v1。均未修改。
