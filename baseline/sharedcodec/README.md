# 共享上下文无损count编码

本轮已完成：[结果与限制](E:/count压缩/baseline/reports/SHARED_MODEL_RESULT.md)。空间100/100包独立匹配，比S0合计小2.497%，中位节省−0.0199%、49胜51负；未达到双门槛。主299/300、复现300/300，顺序对照一次进程异常保留，整体验收inconclusive，不替换默认S0。

固定模型为每基因原S0 Q12边际概率q0，加8概率区间×7邻居非零数的56个odds修正。前6行直接使用q0，后续行只使用已解码的6个前驱。同一模型分别使用原序前驱、原空间前驱及原shuffle11前驱。

每个桶及k单独拟合标量β，目标是带基因logit(q0/4096)偏移的Bernoulli负对数似然总和加β²/2。固定[-8,8]边界及48次二分，无参数搜索。它是当前切片自适应统计模型，完整付费传参，不是未见切片预测验证。

传输R=floor(exp(β)×65536+0.5)，每项uint32，共224字节。区间左闭右开，边界为[1,4,16,64,256,1024,2048,3072,4096]。

整数重建：令D=q0×R+(4096−q0)×65536，q=clip((4096×q0×R+floor(D/2))//D,1,4095)。使用uint64计算，概率表在解码端生成，无需存储G×49表。224字节仅是新增修正参数，原S0概率表、图及封装仍全部计费。

命令从项目根目录执行：

```powershell
python -X utf8 -B baseline/sharedcodec/test_shared.py
python -X utf8 -B baseline/sharedcodec/run.py --smoke --output baseline/evidence/COUNT-SHARED-001/new_smoke
python -X utf8 -B baseline/sharedcodec/run.py --output baseline/evidence/COUNT-SHARED-001/new_run
```

输出目录须不存在。新进程解码后，父进程对形状、CSR指针、索引、原整数值和元数据逐项核对。通过后仅删除自己生成的临时decoded.npz，保留完整包和检查记录，独立复现会重新编码和解码。Python源访问guard及采样资源检查不是OS沙箱。

frozen_runtime三文件原样复制自此前100例runtime，避免修改旧Numba缓存。Pcodec仍使用本机已固定的旧1.0.3二进制依赖，记录在environment.json。模型拟合用浮点，但传输后CDF重建用整数；不声明跨机器拟合得到相同参数。

主门槛是空间共享模型对S0完整包合计至少节省1%、逐样本中位节省为正。空间对同模型前缀及打乱的结果单独解释。失败为NULL，无自动重试，不按结果选择最佳模式。
