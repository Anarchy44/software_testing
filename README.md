# 软件测试与维护大作业复现说明

本项目为“软件测试与维护（2026 年春）”大作业最低标准第三档实现。提交包内已经包含源码、实验数据、实验结果、截图、报告 PDF/DOCX 和展示 PPTX。本文档只说明如何在本地复现实验与重新生成交付物，不包含个人仓库链接或本机绝对路径。

## 1. 项目内容

本项目完成以下内容：

- 选择 Online Boutique 作为比 SockShop 更复杂的开源微服务系统（11 个微服务）。
- 新增 `diagnosis-service` 微服务，用于查询异常检测结果。
- 阅读 Donut 和 FluxEV 两篇 KPI/时序异常检测论文，完成理论对比（VAE vs EVT 方法论差异）。
- 实现轻量版 FluxEV 异常检测流程，包含消融实验验证两步平滑贡献。
- 部署 Prometheus + Grafana 监控栈，配置 ChaosMesh 故障注入（网络延迟/Pod 终止/CPU 压力）。
- 编写 Selenium 功能测试（首页/商品浏览/下单流程）和 JMeter 性能测试计划（50 并发用户）。
- 生成过程截图、实验图、报告 DOCX/PDF 和展示 PPTX。

本项目不做加分项，不额外复现更多论文，也不封装智能体运维。

## 2. 目录结构

```text
.
├── data/                         # 样例 KPI 数据
├── deliverables/                 # 最终报告、PPT 和预览图
├── docs/                         # 论文阅读笔记 (paper_notes.md)
├── k8s/                          # Kubernetes 清单
│   ├── diagnosis-service.yaml    #   新增微服务部署
│   ├── prometheus-config.yaml    #   Prometheus 抓取配置 (ConfigMap)
│   ├── prometheus-deployment.yaml#   Prometheus 部署 + RBAC
│   ├── grafana-deployment.yaml   #   Grafana 部署 + Service
│   ├── grafana-datasource.yaml   #   Grafana 数据源与仪表盘 (ConfigMap)
│   └── chaos-experiments/        #   ChaosMesh 故障实验
│       ├── network-delay.yaml    #     frontend→cartservice 200ms 延迟
│       ├── pod-kill.yaml         #     随机终止 cartservice Pod
│       └── cpu-stress.yaml       #     productcatalogservice 80% CPU 压力
├── outputs/                      # 实验输出、截图、图表
├── scripts/                      # 数据生成、实验运行、报告/PPT素材生成脚本
│   ├── generate_sample_data.py   #   生成 Prometheus 风格 KPI 数据
│   ├── run_fluxev_experiment.py  #   FluxEV 异常检测主实验
│   ├── run_ablation.py           #   消融实验（两步平滑贡献分析）
│   ├── run_fluxev_on_chaos.py    #   故障注入场景下的 FluxEV 检测
│   ├── run_fault_collection.py   #   故障数据采集管道
│   ├── collect_from_prometheus.py#   Prometheus 指标采集
│   ├── verify_deployment.py      #   部署状态验证
│   ├── deploy_online_boutique.sh #   Online Boutique 部署脚本
│   ├── setup_prometheus.sh       #   Prometheus + Grafana 部署脚本
│   ├── setup_chaosmesh.sh        #   ChaosMesh 安装 + 故障实验注入
│   ├── run_jmeter_test.sh        #   JMeter CLI 测试执行脚本
│   ├── build_report.py           #   生成 DOCX 报告
│   ├── build_report_pdf.py       #   生成 PDF 报告
│   └── generate_evidence_assets.py#  生成过程截图
├── services/diagnosis-service/   # 新增微服务源码与 Dockerfile
├── src/fluxev/                   # FluxEV 风格检测器实现
├── tests/                        # 测试代码
│   ├── jmeter/
│   │   └── online_boutique_test.jmx  # JMeter 性能测试计划
│   └── selenium/
│       ├── conftest.py           #   pytest 配置 (headless Chrome)
│       └── test_frontend.py      #   功能测试 (Homepage/Browse/Checkout)
└── slides/                       # PPT 可编辑页面源码
```

## 3. 环境要求

### 3.1 基础环境

- **操作系统**: Windows 10/11, Linux, 或 macOS
- **Python**: 3.10+
- **Docker**: 24.0+ (用于 minikube driver 和 diagnosis-service 镜像构建)
- **kubectl**: 1.28+ (Kubernetes 命令行工具)
- **minikube**: 1.32+ (本地 Kubernetes 集群)
- **Helm**: 3.13+ (用于安装 ChaosMesh)

### 3.2 可选工具

- **Apache JMeter**: 5.6+ (性能测试)
- **Google Chrome**: 120+ (Selenium headless 模式)
- **PowerShell 7** 或 Windows PowerShell (Windows 平台脚本执行)

### 3.3 Python 依赖

```powershell
pip install -r requirements.txt
```

如果只复现实验（不部署 Kubernetes），只需要 Python 依赖即可。

## 4. 四阶段说明

### 阶段一：系统部署 + 论文阅读

1. **论文阅读笔记**: 见 `docs/paper_notes.md`，涵盖 FluxEV 四大组件（EWMA 波动提取 / 两步平滑 / SPOT + MOM-POT 自动阈值 / 参数分析）和 Donut 三大创新（VAE + M-ELBO / MCMC 插值 / KDE 异常分数），含两篇论文对比表。
2. **启动 minikube & 部署 Online Boutique**:

```powershell
minikube start --driver=docker --cpus=4 --memory=6144
```

部署 Online Boutique：

```powershell
# 方式一：提前把 Online Boutique 源码放到 third_party\microservices-demo
# 方式二：设置官方代码源地址，由脚本自动克隆
$env:ONLINE_BOUTIQUE_REPO_URL="<official-online-boutique-source-url>"
.\scripts\deploy_online_boutique.ps1
kubectl get pods -n online-boutique
```

3. **构建并部署 diagnosis-service**:

```powershell
docker build -t diagnosis-service:local .\services\diagnosis-service
minikube image load diagnosis-service:local

kubectl create configmap diagnosis-sample-data `
  --from-file=metrics_with_scores.csv=outputs\metrics_with_scores.csv `
  -n online-boutique `
  --dry-run=client -o yaml | kubectl apply -f -

kubectl apply -f k8s\diagnosis-service.yaml
kubectl rollout status deployment/diagnosis-service -n online-boutique
```

4. **验证部署**:

```powershell
python scripts/verify_deployment.py
```

### 阶段二：Prometheus/Grafana 监控 + ChaosMesh 故障注入

1. **部署 Prometheus + Grafana**:

```powershell
# 方式一：使用脚本
.\scripts\setup_prometheus.sh

# 方式二：手动部署
kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f k8s/prometheus-config.yaml
kubectl apply -f k8s/prometheus-deployment.yaml
kubectl apply -f k8s/grafana-deployment.yaml
kubectl apply -f k8s/grafana-datasource.yaml
```

2. **访问监控面板**:

```powershell
# Prometheus (端口 9090)
kubectl port-forward svc/prometheus 9090:9090 -n monitoring

# Grafana (端口 3000, 用户名/密码: admin/admin)
kubectl port-forward svc/grafana 3000:3000 -n monitoring
```

3. **安装并配置 ChaosMesh**:

```powershell
.\scripts\setup_chaosmesh.sh
```

4. **采集故障数据**:

```powershell
python scripts/run_fault_collection.py
```

### 阶段三：Selenium/JMeter 测试

1. **Selenium 功能测试**:

```powershell
# 先建立 port-forward
kubectl port-forward svc/frontend 8081:80 -n online-boutique

# 运行测试
pytest tests/selenium/ -v
```

测试覆盖：首页加载、商品浏览与详情页、完整下单流程（选商品→Add to Cart→购物车）。

2. **JMeter 性能测试**:

```powershell
# GUI 模式（编辑测试计划）
jmeter -t tests/jmeter/online_boutique_test.jmx

# CLI 非 GUI 模式（执行测试）
.\scripts\run_jmeter_test.sh
# 或直接执行：
jmeter -n -t tests/jmeter/online_boutique_test.jmx `
  -l outputs/jmeter_results.jtl `
  -e -o outputs/jmeter_report
```

测试计划：50 个虚拟用户，30 秒 ramp-up，持续 5 分钟，覆盖 Homepage/Cart/Product Page。

### 阶段四：FluxEV 算法复现与真实数据验证

1. **基础复现实验**:

```powershell
# 生成 KPI 数据
python scripts/generate_sample_data.py

# 运行 FluxEV 异常检测
$env:PYTHONPATH = "$PWD\src"
python scripts/run_fluxev_experiment.py --input data/sample_prometheus_metrics.csv
```

运行后生成：

```text
outputs/metrics_with_scores.csv
outputs/experiment_summary.json
outputs/figures/fluxev_detection_result.png
outputs/figures/fluxev_score_threshold.png
outputs/figures/fluxev_F_vs_S.png
outputs/figures/fluxev_score_distribution.png
```

2. **消融实验**（对应论文 Table 4）:

```powershell
$env:PYTHONPATH = "$PWD\src"
python scripts/run_ablation.py --input data/sample_prometheus_metrics.csv
```

生成 `outputs/ablation_summary.json` 和 `outputs/figures/ablation_comparison.png`。

3. **故障注入场景下的检测**:

```powershell
$env:PYTHONPATH = "$PWD\src"
python scripts/run_fluxev_on_chaos.py --metrics outputs/chaos_metrics.csv --labels outputs/chaos_labels.csv
```

## 5. 复现 FluxEV 异常检测实验

生成 Prometheus 风格 KPI 数据：

```powershell
python scripts/generate_sample_data.py
```

运行 FluxEV 风格异常检测：

```powershell
$env:PYTHONPATH = "$PWD\src"
python scripts/run_fluxev_experiment.py --input data/sample_prometheus_metrics.csv
```

运行后会生成：

```text
outputs/metrics_with_scores.csv
outputs/experiment_summary.json
outputs/figures/fluxev_detection_result.png
outputs/figures/fluxev_score_threshold.png
```

当前提交包内的基本实验结果为：

```text
Precision ≈ 1.000
Recall    ≈ 0.875
F1        ≈ 0.933
```

（精确值取决于 `data/sample_prometheus_metrics.csv` 中的具体注入异常数量和位置，运行后见 `outputs/experiment_summary.json`）

## 6. 本地运行新增微服务

`diagnosis-service` 使用 Python 标准库实现，不依赖 Flask 或数据库。

```powershell
$env:DIAGNOSIS_DATA = "$PWD\outputs\metrics_with_scores.csv"
python services/diagnosis-service/app.py
```

接口：

```text
GET http://127.0.0.1:8080/health
GET http://127.0.0.1:8080/summary
GET http://127.0.0.1:8080/anomalies?limit=20
```

示例验证：

```powershell
python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8080/summary').read().decode())"
```

## 7. Kubernetes 部署复现

启动 minikube：

```powershell
minikube start --driver=docker --cpus=4 --memory=6144
```

部署 Online Boutique：

```powershell
# 方式一：提前把 Online Boutique 源码放到 third_party\microservices-demo
# 方式二：设置官方代码源地址，由脚本自动克隆
$env:ONLINE_BOUTIQUE_REPO_URL="<official-online-boutique-source-url>"
.\scripts\deploy_online_boutique.ps1
kubectl get pods -n online-boutique
```

构建并加载新增微服务镜像：

```powershell
docker build -t diagnosis-service:local .\services\diagnosis-service
minikube image load diagnosis-service:local
```

把实验结果挂载为 ConfigMap：

```powershell
kubectl create configmap diagnosis-sample-data `
  --from-file=metrics_with_scores.csv=outputs\metrics_with_scores.csv `
  -n online-boutique `
  --dry-run=client -o yaml | kubectl apply -f -
```

部署新增服务：

```powershell
kubectl apply -f k8s\diagnosis-service.yaml
kubectl rollout status deployment/diagnosis-service -n online-boutique
```

在 Pod 内验证接口：

```powershell
kubectl exec -n online-boutique deployment/diagnosis-service -- `
  python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8080/summary').read().decode())"
```

## 8. 重新生成截图、报告和 PPT

生成脱敏过程截图：

```powershell
python scripts/generate_evidence_assets.py
```

生成报告 DOCX：

```powershell
python scripts/build_report.py
```

生成报告 PDF：

```powershell
python scripts/build_report_pdf.py
```

生成 PPTX 需要 Codex bundled `@oai/artifact-tool` 运行时。如果本机没有该运行时，可直接使用 `deliverables/` 中已经生成好的 PPTX。

## 9. 最终交付物

最终交付物位于：

```text
deliverables/software_testing_and_maintenance_final_report.pdf
deliverables/software_testing_and_maintenance_final_report.docx
deliverables/software_testing_final_presentation.pptx
```

过程材料位于：

```text
outputs/screenshots/
outputs/figures/
```

压缩提交时建议包含整个项目目录，但排除 `.git/`、`node_modules/`、临时渲染目录和 Python 缓存。
