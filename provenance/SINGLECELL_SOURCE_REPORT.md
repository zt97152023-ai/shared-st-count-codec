# 单细胞 count 无损压缩：3 个公开数据集探索性比较

输入为官方细胞筛选后的完整矩阵，未做归一化、HVG 或细胞子抽样。恢复对象为 canonical int64 count、全部 gene IDs、cell barcodes 及统一的序列兼容字段；不是原 HDF5 文件或全部 feature annotation。

Shared_sequence 复用现有 Shared 概率模型和 rANS；以原文件细胞顺序的前序上下文工作。(row_index, 0) 只用于现有接口兼容，既不是空间坐标，也不是由表达计算的 embedding。该字段在所有方法中相同且计费。参数按现有 Shared 流程从目标矩阵拟合并写入码流，不涉及神经网络预训练。

| 数据集 | 物种/组织 | cells × genes | 非零项 | Shared 字节 | IVCSC+bz2 字节 | Shared 节省 |
|---|---|---:|---:|---:|---:|---:|
| [pbmc_1k_v3](https://www.10xgenomics.com/datasets/1-k-pbm-cs-from-a-healthy-donor-v-3-chemistry-3-standard-3-0-0) | Human/Blood | 1222 × 33538 | 2498225 | 1,638,747 | 2,056,320 | 20.31% |
| [pbmc3k](https://www.10xgenomics.com/datasets/3-k-pbm-cs-from-a-healthy-donor-1-standard-1-1-0) | Human/Blood | 2700 × 32738 | 2286884 | 1,637,081 | 1,983,915 | 17.48% |
| [neuron_1k_v3](https://www.10xgenomics.com/datasets/1-k-brain-cells-from-an-e-18-mouse-v-3-chemistry-3-standard-3-0-0) | Mouse/Brain | 1301 × 31053 | 4220492 | 2,567,949 | 3,271,468 | 21.50% |

配对成功数据集合计：Shared 5,843,777 B，IVCSC+bz2 7,311,703 B，节省 20.08%。

## 全部方法：完整归档字节

| Method | pbmc_1k_v3 | pbmc3k | neuron_1k_v3 |
|---|---:|---:|---:|
| BP_gene_none | 4,129,095 | 3,889,963 | 6,344,201 |
| BP_spot_mean | 3,310,658 | 3,648,097 | 5,111,104 |
| CSC_ZSTD19 | 2,300,587 | 2,261,858 | 3,841,722 |
| CSR_ZSTD19 | 2,816,242 | 3,060,951 | 4,634,642 |
| H5AD_GZIP4 | 7,027,804 | 6,674,034 | 10,769,732 |
| IVCSC | 3,516,712 | 3,244,814 | 5,536,124 |
| IVCSC_bz2 | 2,056,320 | 1,983,915 | 3,271,468 |
| Shared_sequence | 1,638,747 | 1,637,081 | 2,567,949 |

## 解释边界

完成记录 24/24；成功 24；失败 0。真实归档、EXACT.json、独立进程日志与哈希均保留在 main_v2。
只有 3 个数据集、2 类组织、2 个物种，且全部来自 10x；不能推广为全部单细胞平台，也不能把细胞当作独立生物学重复。PBMC 两批供体关系未独立确认。
相同序列兼容元数据实现当前接口口径公平，但并非专为无坐标单细胞设计的最小元数据格式。没有把额外注释或原始 gene 顺序映射计入恢复对象。
压缩率结果不说明机制来源，不证明空间依赖或未训练的神经网络泛化，也不包含 Pcodec/GPress 的比较。
main_v1 在 PBMC3k 准备时因 Matrix Market 数值以 float 存储而停止；main_v2 增加有限、非负、uint32 范围及严格整数性检查后转 int64，未改数值、样本或模型。main_v1 保留，不择优混合。

## 数据来源与追溯

- pbmc_1k_v3: https://www.10xgenomics.com/datasets/1-k-pbm-cs-from-a-healthy-donor-v-3-chemistry-3-standard-3-0-0
  - Download: https://cf.10xgenomics.com/samples/cell-exp/3.0.0/pbmc_1k_v3/pbmc_1k_v3_filtered_feature_bc_matrix.h5
  - Local matrix SHA256: `8191f576550c1b449d03441b9eb098ee9f73fa82513d171ba87d31d551e3ffda`
- pbmc3k: https://www.10xgenomics.com/datasets/3-k-pbm-cs-from-a-healthy-donor-1-standard-1-1-0
  - Download: https://cf.10xgenomics.com/samples/cell-exp/1.1.0/pbmc3k/pbmc3k_filtered_gene_bc_matrices.tar.gz
  - Local matrix SHA256: `12c2fe19e03e2dede77888715e0fd3a1e07e2cdc7a3e138374cc99b0f2a0787b`
  - 原始 tar.gz SHA256: `847d6ebd9a1ec9a768f2be7e40ca42cbfe75ebeb6d76a4c24167041699dc28b5`；本地 HDF5 是无筛选格式转换。
- neuron_1k_v3: https://www.10xgenomics.com/datasets/1-k-brain-cells-from-an-e-18-mouse-v-3-chemistry-3-standard-3-0-0
  - Download: https://cf.10xgenomics.com/samples/cell-exp/3.0.0/neuron_1k_v3/neuron_1k_v3_filtered_feature_bc_matrix.h5
  - Local matrix SHA256: `78166dda24a6103f6b690e0e5a392d89f9da429b84ee265ee4a0f4621f607695`

## 独立核验与重复执行
独立审查见 REVIEW.json。第二轮 24/24 次，exact=True，物理归档字节数相同=True，所有计费文件 SHA256 相同=True。详见 REPRODUCTION.json。
主轮与重复执行的部分阶段并发，时间只作运行记录，不作严格速度排名。
