# 方法—源码映射

|方法步骤|源文件|说明|
|输入与恢复合同|baseline/execution_ready/adapter.py；baseline/evidence/COUNT-E1-100/runtime/io047.py|读取H5AD、canonical CSR、标签、坐标|
|千例K32入口|baseline/evidence/COUNT-HEST-SHARED-K32-001/worker.py|value-only K族、manifest版本标记及匹配解码|
|完整Shared编码|baseline/hest_large_runtime/shared.py|构图、模型估计、支持/正值流、archive|
|因果前驱|baseline/evidence/COUNT-E1-100/runtime/codec.py::graph_for|原row顺序，每行最多6个更早的空间近邻；图实际存储|
|support共享|baseline/sharedcodec/model.py|Q12基准概率、8个support bucket和7个上下文状态|
|support rANS|baseline/qpatchcodec/frozen_runtime/entropy.py|Q12概率及byte-rANS|
|正值分布与条件表|baseline/qpatchcodec/model.py|tail-scale group、singleton odds、32类magnitude频率；K32由worker适配|
|共享singleton中心|baseline/qpatchcodec/qshare_model.py|QSH1 mode0；不等于support分桶|
|正值rANS|baseline/qpatchcodec/values.py|singleton、magnitude、uniform remainder|
|冻结依赖加载|baseline/hest_large_runtime/runtime.py|源码hash校验、私有模块名和Numba加载处理|
|真实解码|baseline/hest_large_runtime/decoder.py + K32 worker|仅归档依赖；metadata与count哈希校验；重建CSR|
|物理计费|baseline/hest_large_runtime/archive.py|payload_streams、paid_model_members、graph_index、identity_coordinates、manifest、zip_framing|
|独立结果比较|baseline/hest1000/pilot.py::compare；K32 worker::verify|dtype、shape、canonical CSR、counts、metadata|
|千例统计|baseline/evidence/COUNT-HEST-SHARED-K32-001/summarize.py|逐样本真实字节、bpc/bpnz、六类账本及配对比较|

这套Shared是统计熵模型，不依赖训练神经网络。神经T0/T1/T2、图像VQ等是独立研究分支，本包不将其混入Production Shared核心。

历史工程代码中存在动态源码替换和路径约束；这里保留原实现以对应已有结果，不悄悄重构它。以后如制作公开软件发行版，重构应作为新版本并单独核对码流等价性。
