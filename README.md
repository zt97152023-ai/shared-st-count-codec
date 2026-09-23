# Count 压缩：当前主线

**方法侧重运行审计：[Reproducibility Freeze v0.1](baseline/reports/reproducibility_freeze_v0_1/README.md)。** 200历史包＋400编码侧资产SHA核验；环境为当前快照，148人工表未填写，新泛化尚未放行。

**验证溯源与冻结协议草案：[Validation Set Design v0.1](baseline/reports/validation_provenance_v0_1/README.md)。** 148条时间线完成，Qpatch阶段日期已定位；首次接触及使用影响未查清，Tier2仍为0，未放行实验。

**验证就绪审计 v0.1：[候选与泄漏报告](baseline/reports/validation_readiness_v0_1/leakage_report.md)。** 1007候选中发现49额外历史压缩接触；148仅为优先溯源池，验证集尚未放行。新信息更新下方inventory历史快照的使用史未知状态。

**资产清单 v0.1：[Data & Experiment Inventory](baseline/reports/inventory_v0_1/README.md)。** 开发100例、验证集未选定、实验注册与claim证据、正式代码版本及冻结边界。只读审计，未移动数据或运行新实验。

**2026-09-10 研究总览：[研究脉络、进展与边界](baseline/reports/RESEARCH_PROGRESS_AND_BOUNDARIES.md)。** 最新Linux三样本G/E/R/F主运行与复现24包全部通过；F比G大140.18%，增量96.49%来自目录和ZIP。下一优先紧凑容器与索引。下方保留历史阶段记录，其中“尚未真实运行”等表述已由最新[完整结果](baseline/reports/DEPENDENCY_POST_REPAIR_RESULTS.md)更新。

**已组建：[st_codec 基线工作台](st_codec/README.md)。** CSR+bz2空间块、精确区域读取、完整字节账本已通过合成验证；G/E/R/F实验适配器已实际编码、独立解码并复现。F逐基因条件拟合缺陷已修复并通过独立标量核验。VQ/seed尚未实现，原三例真实实验未运行。[独立验收](baseline/evidence/COUNT-ASSEMBLY-001/review_result_v2.json)。

**目标：完整保留空间转录组 count、基因/位置身份和坐标，减少实际可解码包的大小。**

**架构设计：[支持区域动态读取的联合压缩框架](E:/count压缩/baseline/reports/ROI_COMPRESSION_DESIGN.md)。** 独立共享空间目录＋固定分块＋块内Qpatch＋独立图像码流。CSR+bz2区域原型已经实现，但旧真实主运行/复现存在超时，未获完整验收；块内Qpatch仍在合成验证阶段。精确图像ROI须补足像素坐标映射。

**最新小试：[图像元数据共享与空间图重建](E:/count压缩/baseline/reports/SPATIAL_SHARE_RESULT.md)。** 固定3例×4对照，主运行及独立复现各12/12精确还原，12包SHA一致；图像和count码流/模型全部不变。组合净省52,714 B（联合包0.004322%，3胜）；图像元数据共享单独省35,393 B，通用图重建省83,950 B，新通用布局增加66,629 B。共享后的元数据仍比旧格式大30,410 B，10.75%收益仅相对同格式inline对照。验证了共享描述的增量，当前整体幅度小；未扩100，不改变Qpatch count主线。[实现](E:/count压缩/baseline/spatialsharecodec/README.md) · [独立核验](E:/count压缩/baseline/evidence/COUNT-SPATIAL-SHARE-001/VERIFICATION.json)。

**前次图像条件小试：[已解码图像条件](E:/count压缩/baseline/reports/IMAGE_CONDITION_RESULT.md)。** 固定SPA108/NCBI807/TENX132，原模型/真实亮度条件/打乱条件三arm，主运行及独立复现各9/9完整count与RGBpatch集合无损，9包SHA一致。真实图像相对基线净省3,045 B，占1.22GB联合包仅0.00024966%；相对打乱数值流＋参数省2,515 B，三项预定正收益检查通过。幅度很小，TENX132仍增202 B；仅是固定亮度条件的三例开发信号，非WSI压缩或实用突破，不默认替换下方count主线，也未扩到100例。

**最新实测：[Qpatch12完整文件验证](E:/count压缩/baseline/reports/QPATCH_CODEC_RESULT.md)。** 固定共享概率及12bit付费修正规则，重新编码全部正值流；主运行和独立复现各100/100精确恢复，100实际包SHA一致。完整包310,818,385→309,538,122 B，净省1,280,263 B（0.4119%），逐片中位省1.8849%，99胜1负。模型省1,360,916 B，正值流增75,914 B，封装增4,739 B；原34退步例中27例反超V0。唯一相对V2退步TENX73增加14 B，仍有7例落后V0。全模型/图/封装计费，保留空间条件；固定原100开发证据，不调参、不扩样。[实现](E:/count压缩/baseline/qpatchcodec/README.md) · [独立核验](E:/count压缩/baseline/evidence/COUNT-QPATCH-001/VERIFICATION.json)。

以下保留此前筛查与诊断的历史边界，最新完整码流证据见上方。

**当前探索：[保留空间条件的共享概率与付费修正](E:/count压缩/baseline/reports/QSHARE_SCREEN_RESULT.md)。** 原100×2概率参数筛查及独立复现完成，200个实际参数文件SHA一致。Qpatch12将q1描述从2,404,214 B降至1,043,298 B；扣除保守NLL损失预算后约余1,158,629 B，99/100预算为正，原34退步例全部为正。空间图/赔率规则保留；这是参数文件与理论码长上界的筛查，尚未生成新count码流，不能视为实际完整包率已提升。纯共享未过全100保守门槛，未追加调参。

**最新分析：[34个退步样本的原因](E:/count压缩/baseline/reports/VALUE_REGRESSION_DIAGNOSIS.md)。** 34例正值码流全部缩短，合计省403,326 B，但新增模型731,105 B、封装34,767 B，完整包净增362,546 B。模型费用83.68%来自逐基因取1概率q1表。退步组每基因正值观测数较少，小计数比例较高；同平台分析与反例均保留。下一优先是降低逐基因参数的描述成本，暂不增加尾部分组；本次仅复算已有证据，没有新codec实验。

**当前结果：[基因异构正值编码](E:/count压缩/baseline/reports/VALUE_HETEROGENEITY_RESULT.md)。** 原100例×3方法主运行及独立复现各300/300成功，300实际包SHA一致。逐基因singleton概率＋8个尾尺度组＋共享空间条件表，完整包310,818,385字节，比上一轮共享空间编码器小9.3143%，比S0小11.5787%；新增模型2,913,055字节，正值流减少34,939,475字节。预设开发门槛通过；收益不均：相对上一轮Visium48/50改善，传统Spatial Transcriptomics16/48改善、中位增大2.6161%，不能默认所有样本替换。全部参数入账、精确恢复count；已暴露数据不支持泛化结论。[实现与异构性说明](E:/count压缩/baseline/valuecodec/README.md)。

以下保留此前实验的原结论：

**最新实测：[56共享参数实验](E:/count压缩/baseline/reports/SHARED_MODEL_RESULT.md)。** 空间模型100/100包独立匹配，总计342,742,376字节，比S0小2.497%；相对原S2模型存储省17,419,625字节，位置码流仅增1,419,686字节，参数共享的净收益成立。但对S0中位节省为−0.0199%、49胜51负，未过双门槛；主运行299/300、复现300/300，顺序对照有一次编码进程异常，整体验收inconclusive。保留候选，不默认替换S0。

**最新实测：[概率表存储实验结果](E:/count压缩/baseline/reports/TABLE_STORAGE_RESULT.md)。** 原100例S1/S2共200新包独立复现一致；在q和所有数据流不变时，固定28槽先验残差布局使S2表从19.62 MB增至25.95 MB，完整包365.06 MB，比S0大3.85%，8/100胜。该变换无损但不采纳；结果没有否定重新拟合共享概率模型。

**此前算法分析入口：[从全部结果反推算法问题](E:/count压缩/baseline/reports/ALGORITHM_SYNTHESIS.md)。** 按组件账本解释S0、空间模型、IVCSC与旧神经结果，并区分实测、反事实及未来假设。其后已完成表存储及共享模型两个固定实验，最新结论见上方。

## IVCSC 已补充：同100样本

官方IVCSC原生及独立命名的IVCSC_bz2均已完成100/100无损恢复，独立第二次运行的200个完整包大小与SHA256全部一致，600项参考身份核对通过。完整包合计分别695,537,776与419,947,535字节；后者比Pcodec合计小6.75%，但仅48/100胜、样本中位反而大0.81%，仍比S0合计大19.47%，0/100胜。因此保留为表示及归档对照，当前主线不替换S0。

[IVCSC完整报告](E:/count压缩/baseline/IVCSC_REPORT.md)包括方法、分平台结果、限制与复现入口；[补充比较库](E:/count压缩/baseline/evidence/COUNT-IVCSC-100/comparison.sqlite)含五方法500行及实际包路径，旧历史库保留。

## 100样本已测试，完整复现验收未通过

按用户要求，COUNT-E1-100在原100样本上重跑同一8方法，共800组。当前输出在[main_v2](E:/count压缩/baseline/evidence/COUNT-E1-100/main_v2)，每例保存完整包及独立解码检查；配置见[固定100样本](E:/count压缩/baseline/configs/COUNT-E1-100.json)。仅提高独立runtime规模上限以覆盖NCBI652；原试验与中断记录保留。首次796/800成功，四项单次复测成功；独立第二次运行797/800成功，仍有三项运行异常，完整复现验收未通过。797个成功包SHA完全一致；S0/Pcodec等六方法各100匹配，S0合计节省21.94%、94/100胜；空间门槛未过。[100样本报告](E:/count压缩/baseline/EXPERIMENT_RESULT_100.md)保留全部失败与分平台结果。

## 首轮新实验已完成

3个已暴露样本×8方法全部无损恢复，独立复现的24个包大小与SHA256完全一致。简单基因边际模型相对本轮Pcodec合计节省26.13%；空间模型相对原序前缀反而增加0.56%，未过预设门槛。三样本开发结果不代表全库优势。详见[首轮实验报告](E:/count压缩/baseline/EXPERIMENT_RESULT.md)。

## 历史结果：100样本基线已核实

047有八条路线完整覆盖100样本。当前核心比较：

|方法|100例完整包合计字节|相对G0节省|
|---|---:|---:|
|Pcodec|473,695,216|28.99%|
|CSR+BZip2|548,608,925|17.75%|
|G0|667,041,355|参照|

逐样本最小包由Pcodec/G0分别取得77/23例。事后选择最小包只比固定Pcodec再省2.46%，尚未计选择开销。cellstream为21成功/4失败/75未尝试，单列、不进全100榜。来源hash和统计复算已核对；本轮未重跑821项codec解码。数据已暴露，属于描述性结果。

旧051仅INT7实验另组保留，不与047混榜。

## 现在只推进一条研究线

**先解释强编码器的适用边界，再验证空间信息增量。** 不再只围绕G0或INT7改support。045保留为表示机制子实验，不是完整研究路线。

当前依次处理：

1. 利用现有Pcodec/G0/CSR结果解释胜负与反例，不重复跑已有基线。
2. 有限地分离稀疏表示、后端、值与尾部的影响。
3. 在强非空间基线之上检验真实空间排列/上下文的净增量。复杂router暂不优先。

H&E、联合容器、渐进读取和新网络暂不进入当前工作队列。原始数据与历史证据留在原位置。

## 主要入口

- [当前实验计划](E:/count压缩/baseline/EXPERIMENT_PLAN.md)：分阶段 baseline、因果解码约束、净字节指标与停止条件；E1三样本闭环已完成，暂不扩样或训练网络。
- [已发表相关工作](E:/count压缩/baseline/reports/PUBLISHED_RELATED_WORK.md)：正式期刊/会议文献、发表状态核实、直接竞争与可借鉴机制。
- [算法调研与结合方案](E:/count压缩/baseline/reports/ALGORITHM_INTEGRATION_RESEARCH.md)：机器学习与传统候选、接入位置、优先级和最小验证实验。
- [方法详细报告](E:/count压缩/baseline/reports/METHODS_DETAILED_REPORT.md)：原12个方法定义、编码原理、具体实现、优劣案例和分析图；新增方法见[IVCSC补充](E:/count压缩/baseline/IVCSC_REPORT.md)。
- [Baseline比较表](E:/count压缩/baseline/results/current/COMPARISON.md)：分组排名、覆盖与失败。
- [压缩架构](E:/count压缩/baseline/ARCHITECTURE.md)：可替换codec、统一对象与独立验证。
- [三个科研问题](E:/count压缩/baseline/RESEARCH.md)：假设、竞争解释、对照与失败规则。
- [数据集总结](E:/count压缩/DATA.md)：1,108 个本地条目、100 样本实验面板、平台/组织构成与文件核验；[方法取舍](E:/count压缩/METHODS.md)。

关键原记录精简导入到 [evidence](E:/count压缩/evidence)。来源哈希见 [SOURCE_MANIFEST.json](E:/count压缩/evidence/SOURCE_MANIFEST.json)。目录盘点和清理记录收进 `.audit`，不作为日常阅读材料。

baseline注册表现含15项（含IVCSC、IVCSC_bz2及S0）；历史SQLite快照为原12方法、906条结果，新IVCSC比较库为五方法500行，按不同实验口径分别查询。旧codec不声称已全部移植；F盘旧项目与原始数据未改动。
