# Donut 实验执行报告

## 执行状态

### ✅ 已完成
1. **Donut 完整实现** (src/donut/)
   - VAE 模型（Encoder-Decoder 架构）
   - M-ELBO 损失函数
   - MCMC 插补算法
   - KDE 异常评分
   
2. **GPU 环境配置**
   - requirements_gpu.txt
   - Dockerfile.gpu (CUDA 11.8)
   
3. **实验脚本**
   - run_donut_experiment.py（主实验）
   - run_donut_vs_fluxev.py（对比实验）
   - run_donut_demo.sh（快速演示）

4. **文档**
   - docs/DONUT_GUIDE.md（完整使用指南）

### ⚠️ 遇到的问题

#### 问题 1: PyTorch 版本兼容性
- **现象**: `torch.rand_like(generator=...)` 在 PyTorch 1.13 不支持
- **修复**: 添加 try-except 回退机制
- **状态**: ✅ 已修复

#### 问题 2: DataLoader 返回类型
- **现象**: `batch_x.to(device)` 报错，DataLoader 返回 list 而非 tensor
- **修复**: 添加 `batch[0] if isinstance(batch, list) else batch`
- **状态**: ✅ 已修复

#### 问题 3: 训练数值不稳定 (NaN)
- **现象**: Loss 变为 NaN
- **根因**: 
  - logvar 值过大导致溢出
  - 缺少梯度裁剪
- **修复**: 
  - 在 encode() 中 clamp logvar 到 [-10, 10]
  - 在 trainer 中添加 gradient clipping (max_norm=1.0)
  - 在 M-ELBO 中 clamp logvar
- **状态**: ✅ 已修复（小规模测试通过）

#### 问题 4: 数据标签策略不合理
- **现象**: 80% 窗口被标记为异常（实际只有 1.1% 的点是异常）
- **根因**: 使用 `window.max()` 标注，任何一个窗口包含单个异常点就被标记
- **修复**: 改用窗口中心点的标签 `df["is_anomaly"].iloc[center_idx]`
- **状态**: 🔄 待验证

### 📊 测试结果

**小规模合成数据测试**（100 样本，60 维窗口）:
```
Training Donut VAE on cpu
Epoch 10/10 - Loss: 0.0434
SUCCESS: Donut training works!
```

✅ VAE 训练正常，Loss 收敛

### 🔧 当前环境

```
PyTorch: 1.13.1+cpu (无 CUDA)
Platform: Windows
Python: 3.10
```

---

## 下一步建议

### 方案 A: 使用 GPU 环境（推荐）

由于本地是 CPU 模式，训练速度较慢。建议使用 Docker GPU 环境：

```bash
# 构建 GPU 镜像
docker build -f Dockerfile.gpu -t donut-gpu .

# 运行容器
docker run --gpus all -it donut-gpu bash

# 在容器内运行实验
python scripts/run_donut_experiment.py \
    --input data/sample_prometheus_metrics.csv \
    --window-size 120 \
    --epochs 100 \
    --batch-size 64
```

### 方案 B: 继续在 CPU 上运行（较慢）

修复标签策略后重新运行：

```bash
# 确保使用最新的代码
git pull

# 运行实验（CPU 模式，约需 30-60 分钟）
python scripts/run_donut_experiment.py \
    --input data/sample_prometheus_metrics.csv \
    --window-size 120 \
    --epochs 50 \
    --batch-size 32
```

### 方案 C: 使用更小的数据集快速验证

```bash
# 生成小规模测试数据
python -c "
import numpy as np
import pandas as pd
n = 200
df = pd.DataFrame({
    'timestamp': pd.date_range('2026-06-10', periods=n, freq='min'),
    'service': 'frontend',
    'metric': 'latency_p95',
    'value': np.random.randn(n) * 20 + 200,
    'is_anomaly': 0
})
# 注入 3 个异常点
df.loc[50, 'value'] += 100
df.loc[100, 'value'] -= 80
df.loc[150, 'value'] += 120
df.loc[[50, 100, 150], 'is_anomaly'] = 1
df.to_csv('data/small_test.csv', index=False)
"

# 快速测试
python scripts/run_donut_experiment.py \
    --input data/small_test.csv \
    --window-size 60 \
    --epochs 30 \
    --batch-size 16
```

---

## 预期输出

成功运行后将生成：

```
outputs/donut/
├── experiment_summary.json     # Precision/Recall/F1
├── training_history.json       # Loss curves
└── figures/
    ├── donut_training_and_detection.png
    ├── donut_score_timeline.png
    └── donut_vs_fluxev.png     # 如果运行对比实验
```

---

## 代码提交状态

所有修复已提交并推送：

```bash
git commit -m "fix: Donut numerical stability and compatibility fixes"
git push origin main
```

---

*生成时间: 2026-06-14*
*下次执行建议: 使用 GPU 环境或等待 CPU 训练完成*
