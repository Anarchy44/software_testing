# 演示操作手册

本文档为手动操作指南，无需 AI 协助即可独立完成全部演示流程。

---

## 目录

1. [前置条件](#1-前置条件)
2. [阶段一：环境检查与集群启动](#2-阶段一环境检查与集群启动)
3. [阶段二：部署微服务系统](#3-阶段二部署微服务系统)
4. [安装 Istio（服务网格 + Sidecar）](#4-安装-istio服务网格--sidecar-指标暴露)
5. [阶段三：部署监控栈 Prometheus + Grafana](#5-阶段三部署监控栈-prometheus--grafana)
6. [阶段四：部署 ChaosMesh 故障注入](#6-阶段四部署-chaosmesh-故障注入)
7. [阶段五：Selenium 功能测试](#7-阶段五selenium-功能测试)
8. [阶段六：JMeter 性能测试](#8-阶段六jmeter-性能测试)
9. [阶段七：FluxEV 异常检测实验](#9-阶段七fluxev-异常检测实验)
10. [阶段八：消融实验](#10-阶段八消融实验)
11. [阶段九：生成报告](#11-阶段九生成报告)
12. [附录：截图清单](#12-附录截图清单)

---

## 1. 前置条件

### 1.1 环境要求

| 组件 | 最低版本 | 验证命令 |
|------|----------|----------|
| Docker Desktop | 24.0+ | `docker --version` |
| kubectl | 1.28+ | `kubectl version --client` |
| minikube | 1.32+ | `minikube version` |
| Helm | 3.13+ | `helm version` |
| Python | 3.10+ | `python --version` |
| Apache JMeter | 5.6+ | `jmeter --version` |
| Microsoft Edge | 120+ | Selenium headless 模式需要（Windows 10/11 预装） |

### 1.2 代理配置

如果在中国大陆网络环境下，需要为 Docker Desktop 配置代理以拉取镜像：

1. 打开 Docker Desktop → Settings → Resources → Proxies
2. 填入 HTTP/HTTPS 代理：
   ```
   HTTP Proxy:  http://127.0.0.1:<你的代理端口>
   HTTPS Proxy: http://127.0.0.1:<你的代理端口>
   ```
3. Apply & Restart

### 1.3 Python 依赖

```powershell
cd <项目根目录>
pip install -r requirements.txt
```

> 所需包：numpy, pandas, matplotlib, scikit-learn, python-docx, reportlab, selenium, pytest

---

## 2. 阶段一：环境检查与集群启动

### 2.1 环境检查

```powershell
docker --version
kubectl version --client
minikube version
python --version
```

**期望输出**：以上命令均应输出版本号，无报错。

> 📸 **截图点 1** — 终端环境检查结果

---

### 2.2 确保 Docker Desktop 正在运行

检查系统任务栏 Docker 图标是否为 "Engine running" 状态。

```powershell
docker info --format '{{.ServerVersion}}'
```

**期望输出**：Docker 版本号（如 `29.4.1`）。

---

### 2.3 启动 minikube

```powershell
minikube start --driver=docker --cpus=4 --memory=6144
```

**期望输出**：
```
* Done! kubectl is now configured to use "minikube" cluster
```

验证集群状态：

```powershell
minikube status
kubectl get nodes
```

**期望输出**：`minikube Ready control-plane`

> 📸 **截图点 2** — `kubectl get nodes` 输出

---

## 3. 阶段二：部署微服务系统

### 3.1 部署 Online Boutique（11 个微服务）

```powershell
kubectl apply -f https://raw.githubusercontent.com/GoogleCloudPlatform/microservices-demo/main/release/kubernetes-manifests.yaml
```

如需从本地文件部署：

```powershell
# 先克隆仓库
git clone --depth 1 https://github.com/GoogleCloudPlatform/microservices-demo.git third_party/microservices-demo
# 部署
kubectl apply -f third_party/microservices-demo/release/kubernetes-manifests.yaml
```

### 3.2 等待所有 Pod 就绪

```powershell
kubectl wait --for=condition=available deployment --all --timeout=300s
```

### 3.3 验证部署

```powershell
kubectl get pods
kubectl get svc
```

**期望输出**：12 个 Pod 全部 `Running`，13 个 Service。

> 📸 **截图点 3** — `kubectl get pods` 输出（全 Running）

---

### 3.4 验证前端可访问性

```powershell
kubectl port-forward svc/frontend 8081:80
```

另开终端：

```powershell
curl.exe -s -o NUL -w "HTTP %{http_code}" http://localhost:8081
```

**期望输出**：`HTTP 200`

浏览器访问 http://localhost:8081 ，确认看到 Online Boutique 首页（Hot Products 商品列表）。

> 📸 **截图点 4** — Online Boutique 首页浏览器截图

---

### 3.5 构建并部署 diagnosis-service

**3.5.1 构建镜像**

```powershell
cd <项目根目录>
docker build -t diagnosis-service:local services/diagnosis-service
```

**3.5.2 加载到 minikube**

```powershell
minikube image load diagnosis-service:local
```

**3.5.3 部署到 K8s**

```powershell
kubectl apply -f k8s/diagnosis-service.yaml
kubectl rollout status deployment/diagnosis-service -n online-boutique
```

**3.5.4 验证诊断服务**

```powershell
kubectl exec -n online-boutique deployment/diagnosis-service -- python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8080/health').read().decode())"
```

**期望输出**：`{"status": "ok", "data_exists": true}`

> 📸 **截图点 5** — `health` 和 `summary` 端点输出

```powershell
kubectl exec -n online-boutique deployment/diagnosis-service -- python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8080/summary').read().decode())"
```

---

### 3.6 集群概览验证

```powershell
kubectl get pods -A
kubectl get svc -A
```

> 📸 **截图点 6** — 集群全貌（所有命名空间的 Pod + Service）

---

## 4. 安装 Istio（服务网格 + Sidecar 指标暴露）

### 4.0 为什么需要 Istio？

Online Boutique 的 9 个核心微服务使用 **gRPC 协议**（非 HTTP），Prometheus 无法直接抓取。Istio 在每个 Pod 中注入 `istio-proxy` sidecar（端口 15020），向 Prometheus 暴露标准的 HTTP `/stats/prometheus` 端点。

### 4.1 下载 istioctl

**Windows (PowerShell):**
```powershell
Invoke-WebRequest -Uri "https://github.com/istio/istio/releases/download/1.22.0/istio-1.22.0-win.zip" -OutFile istio.zip
Expand-Archive istio.zip -DestinationPath .
cd istio-1.22.0
$env:PATH = "$PWD\bin;$env:PATH"
```

**Linux / macOS / Git Bash:**
```bash
curl -L "https://github.com/istio/istio/releases/download/1.22.0/istio-1.22.0-linux-amd64.tar.gz" -o istio.tar.gz
tar xzf istio.tar.gz
export PATH="$PWD/istio-1.22.0/bin:$PATH"
```

### 4.2 安装 Istio（demo 配置）

```powershell
istioctl install --set profile=demo -y
```

**期望输出**：
```
✔ Istio core installed
✔ Istiod installed
✔ Ingress gateways installed
✔ Egress gateways installed
✔ Installation complete
```

### 4.3 启用 Sidecar 注入

```powershell
kubectl label namespace default istio-injection=enabled --overwrite
```

### 4.4 重新部署 Online Boutique（注入 sidecar）

```powershell
kubectl rollout restart deployment -n default
```

等待 Pod 重启并注入 sidecar：

```powershell
kubectl get pods -n default -w
```

**期望输出**：每个 Pod 显示 `2/2 READY`（app 容器 + istio-proxy 容器），约需 1-2 分钟。

> 📸 **截图点 6a** — `kubectl get pods -n default` 显示全部 2/2 READY

### 4.5 验证 Istio sidecar 指标

```powershell
kubectl exec -n default deployment/frontend -c istio-proxy -- curl -s localhost:15020/stats/prometheus | Select-Object -First 20
```

**期望输出**：大量 `istio_` / `envoy_` 开头的 Prometheus 指标。

---

## 5. 阶段三：部署监控栈 Prometheus + Grafana

### 5.1 创建命名空间

```powershell
kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -
```

### 5.2 部署 Prometheus（新配置：Kubernetes SD + Istio sidecar）

```powershell
kubectl apply -f k8s/prometheus-config.yaml
kubectl apply -f k8s/prometheus-deployment.yaml
kubectl rollout status deployment/prometheus -n monitoring --timeout=60s
```

> **重要变更**：Prometheus 配置已从静态 gRPC target 改为 Kubernetes Service Discovery，自动发现所有含 `istio-proxy` 容器的 Pod 并抓取 `:15020/stats/prometheus`。

### 5.3 部署 Grafana

```powershell
kubectl apply -f k8s/grafana-deployment.yaml
kubectl apply -f k8s/grafana-datasource.yaml
kubectl rollout status deployment/grafana -n monitoring --timeout=60s
```

### 5.4 验证监控栈

```powershell
kubectl get pods -n monitoring
```

**期望输出**：prometheus + grafana 均为 `Running`

### 5.5 端口转发与验证

```powershell
# Prometheus
kubectl port-forward svc/prometheus 9090:9090 -n monitoring
```

浏览器访问 http://localhost:9090/targets 查看所有抓取目标。

**期望**：`istio-proxy` job 下的所有目标状态为 **UP**（不再像之前全部 DOWN）。

> 📸 **截图点 7** — Prometheus Targets 页面（istio-proxy 全部 UP）

```powershell
# Grafana
kubectl port-forward svc/grafana 3000:3000 -n monitoring
```

浏览器访问 http://localhost:3000 ，用户名/密码：`admin/admin`，导航到 Dashboards → Online Boutique Monitoring。

**期望**：p95 延迟、请求速率、CPU/内存面板均有实时数据曲线。

> 📸 **截图点 8** — Grafana Online Boutique Monitoring 仪表盘（有数据）

---

## 6. 阶段四：部署 ChaosMesh 故障注入

### 6.1 安装 ChaosMesh（通过 Helm）

```powershell
helm repo add chaos-mesh https://charts.chaos-mesh.org
helm install chaos-mesh chaos-mesh/chaos-mesh --namespace=chaos-testing --create-namespace --version 2.8.2
```

等待 Pod 就绪：

```powershell
kubectl wait --for=condition=available deployment --all -n chaos-testing --timeout=120s
```

### 6.2 手动注入故障（演示用）

> ChaosMesh 实验已改为**手动触发**（无 cron 定时），便于演示时精确控制。

```powershell
# 1) 网络延迟：frontend → cartservice 200ms 延迟（持续10分钟）
kubectl apply -f k8s/chaos-experiments/network-delay.yaml

# 等待 1-2 分钟，观察 Grafana 中 Request Latency p95 明显上升后截图。
# 清除故障：kubectl delete -f k8s/chaos-experiments/network-delay.yaml

# 2) Pod 终止：随机杀一个 cartservice Pod（持续3分钟）
kubectl apply -f k8s/chaos-experiments/pod-kill.yaml

# 等待 1-2 分钟，观察 Grafana 中 Error Rate 出现尖峰后截图。
# 清除故障：kubectl delete -f k8s/chaos-experiments/pod-kill.yaml

# 3) CPU 压力：productcatalogservice 80% CPU 负载（持续10分钟）
kubectl apply -f k8s/chaos-experiments/cpu-stress.yaml

# 观察 Grafana 中 CPU Usage 明显上升后截图。
# 清除故障：kubectl delete -f k8s/chaos-experiments/cpu-stress.yaml
```

或使用快捷脚本：

```powershell
bash scripts/inject_fault.sh network-delay   # 注入网络延迟
bash scripts/inject_fault.sh pod-kill        # 注入 Pod 终止
bash scripts/inject_fault.sh cpu-stress      # 注入 CPU 压力
```

### 6.3 查看故障状态

```powershell
kubectl get networkchaos,podchaos,stresschaos -A
```

> 📸 **截图点 9** — ChaosMesh 故障实验状态

> 📸 **截图点 9a** — Grafana p95 延迟面板（故障注入前后对比）

> 📸 **截图点 9b** — Grafana 错误率面板（pod-kill 尖峰）

> 📸 **截图点 9c** — Grafana CPU Usage 面板（cpu-stress 飙升）

---

## 7. 阶段五：Selenium 功能测试

### 7.0 准备 EdgeDriver

测试默认使用 **Microsoft Edge** 浏览器 headless 模式（Windows 10/11 预装）。Selenium Manager 会自动从 Microsoft CDN 下载匹配的 EdgeDriver。

**如果自动下载失败**（网络受限），手动下载 EdgeDriver：

1. 查看 Edge 版本：打开 Edge → 设置 → 关于 Microsoft Edge，或运行：
   ```powershell
   (Get-Item "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe").VersionInfo.ProductVersion
   ```
2. 从 Microsoft 官网下载匹配版本的 EdgeDriver：
   https://developer.microsoft.com/en-us/microsoft-edge/tools/webdriver/
3. 解压后设置环境变量：
   ```powershell
   $env:EDGEDRIVER_PATH = "C:\path\to\msedgedriver.exe"
   ```

### 7.1 确保前端端口转发已建立

```powershell
kubectl port-forward svc/frontend 8081:80
```

### 7.2 运行测试

```powershell
cd <项目根目录>
pytest tests/selenium/ -v
```

**期望输出**：
```
tests/selenium/test_frontend.py::TestHomepage::test_homepage_loads PASSED
tests/selenium/test_frontend.py::TestProductBrowse::test_product_page_loads PASSED
tests/selenium/test_frontend.py::TestCheckoutFlow::test_checkout_flow PASSED
```

> 📸 **截图点 10** — pytest 测试结果（包含页面加载时间）

---

## 8. 阶段六：JMeter 性能测试

### 8.1 GUI 模式（查看/编辑测试计划）

```powershell
jmeter -t tests/jmeter/online_boutique_test.jmx
```

> 📸 **截图点 11** — JMeter GUI 中测试计划结构（Thread Group + HTTP 采样器）

### 8.2 CLI 模式（执行测试）

```powershell
jmeter -n -t tests/jmeter/online_boutique_test.jmx -l outputs/jmeter_results.jtl -e -o outputs/jmeter_report
```

### 8.3 查看结果

```powershell
# 查看聚合报告
ls outputs/jmeter_report/
# 浏览器打开 outputs/jmeter_report/index.html
```

> 📸 **截图点 12** — JMeter 聚合报告（可选）

---

## 9. 阶段七：FluxEV 异常检测实验

### 9.1 生成样本数据

```powershell
cd <项目根目录>
python scripts/generate_sample_data.py
```

**期望输出**：`wrote ...\data\sample_prometheus_metrics.csv`

### 9.2 运行 FluxEV 检测

```powershell
# Windows PowerShell
$env:PYTHONPATH = "$PWD\src"
python scripts/run_fluxev_experiment.py --input data/sample_prometheus_metrics.csv

# Git Bash / Linux
PYTHONPATH="$(pwd)/src" python scripts/run_fluxev_experiment.py --input data/sample_prometheus_metrics.csv
```

**期望输出**：
```
Data points: 720
Parameters: l=60 s=5 alpha=0.4 d=1 p=2 k=150
{
  "points": 720,
  "true_anomalies": 8,
  "predicted_anomalies": 13,
  "threshold": 3.548,
  "precision": 0.615,
  "recall": 1.000,
  "f1": 0.762,
  ...
}
```

> 📸 **截图点 13** — 终端中 FluxEV 实验结果 JSON

### 9.3 查看生成图表

生成的文件位于：
- `outputs/figures/fluxev_detection_result.png` — 检测结果总览
- `outputs/figures/fluxev_score_threshold.png` — 异常分数与阈值
- `outputs/figures/fluxev_F_vs_S.png` — 两步平滑对比
- `outputs/figures/fluxev_score_distribution.png` — 分数分布

> 📸 **截图点 14** — 以上 4 张实验图表

---

## 10. 阶段八：消融实验

### 10.1 运行消融实验

```powershell
# Windows PowerShell
$env:PYTHONPATH = "$PWD\src"
python scripts/run_ablation.py --input data/sample_prometheus_metrics.csv

# Git Bash / Linux
PYTHONPATH="$(pwd)/src" python scripts/run_ablation.py --input data/sample_prometheus_metrics.csv
```

**期望输出**：
```
=== FluxEV Ablation Study ===
Data: 720 points, period=60

  No smoothing:
    Precision=0.5000  Recall=0.6250  F1=0.5556  Threshold=...
  First-step only (Delta_sigma):
    Precision=0.6000  Recall=0.7500  F1=0.6667  Threshold=...
  Two-step (full FluxEV):
    Precision=...  Recall=...  F1=...  Threshold=...
```

> 📸 **截图点 15** — 终端中消融实验三变体对比表格

### 10.2 查看消融对比图

- `outputs/figures/ablation_comparison.png` — 三变体 Precision/Recall/F1 柱状图

> 📸 **截图点 16** — 消融实验柱状图

---

## 11. 阶段九：生成报告

### 11.1 生成 DOCX 报告

```powershell
cd <项目根目录>
python scripts/build_report.py
```

**期望输出**：`deliverables\software_testing_and_maintenance_final_report.docx`

### 11.2 生成 PDF 报告

```powershell
python scripts/build_report_pdf.py
```

**期望输出**：`deliverables\software_testing_and_maintenance_final_report.pdf`

### 11.3 验证交付物

```powershell
ls -lh deliverables/*.docx deliverables/*.pdf
```

> 📸 **截图点 17** — 终端中报告生成输出 + 文件大小

---

## 12. 附录：截图清单

| 编号 | 截图内容 | 阶段 | 文件保存路径 |
|------|----------|------|-------------|
| `01` | 环境检查（docker/kubectl/minikube/python 版本） | 2.1 | 终端截屏 |
| `02` | `kubectl get nodes` 集群就绪 | 2.3 | 终端截屏 |
| `03` | `kubectl get pods` 全 Running | 3.3 | 终端截屏 |
| `04` | Online Boutique 首页（浏览器） | 3.4 | `outputs/screenshots/online_boutique_frontend.png` |
| `05` | diagnosis-service health 端点 | 3.5 | 终端截屏 |
| `06` | `kubectl get pods -A` 集群全貌 | 3.6 | 终端截屏 |
| `06a`| `kubectl get pods -n default` 全部 2/2 READY | 4.4 | 终端截屏 |
| `07` | Prometheus Targets 页面（istio-proxy 全部 UP） | 5.5 | `outputs/screenshots/prometheus_targets.png` |
| `08` | Grafana Online Boutique Monitoring 仪表盘（有数据） | 5.5 | `outputs/screenshots/grafana_dashboard.png` |
| `09` | ChaosMesh 故障实验 `kubectl get` 状态 | 6.3 | 终端截屏 |
| `09a`| Grafana p95 延迟面板（network-delay 前后对比） | 6.2 | Grafana 截图 |
| `09b`| Grafana 错误率面板（pod-kill 尖峰） | 6.2 | Grafana 截图 |
| `09c`| Grafana CPU Usage 面板（cpu-stress 飙升） | 6.2 | Grafana 截图 |
| `10` | Selenium pytest 结果 | 7.2 | 终端截屏 |
| `11` | JMeter 测试计划结构（GUI） | 8.1 | 终端截屏 / GUI 截图 |
| `12` | JMeter 聚合报告（可选） | 8.3 | 浏览器截图 |
| `13` | FluxEV 实验结果 JSON | 9.2 | 终端截屏 |
| `14` | FluxEV 图表（4 张） | 9.3 | `outputs/figures/fluxev_*.png` |
| `15` | 消融实验三变体对比表 | 10.1 | 终端截屏 |
| `16` | 消融实验柱状图 | 10.2 | `outputs/figures/ablation_comparison.png` |
| `17` | 报告生成 + 交付物列表 | 11.3 | 终端截屏 |

---

## 故障排查

| 问题 | 原因 | 解决方法 |
|------|------|----------|
| 镜像拉取失败 `ImagePullBackOff` | minikube VM 内无代理 | 主机 `docker pull` 后 `minikube image load` |
| Pod 只有 `1/1` 没有 `2/2` | Istio sidecar 未注入 | 检查 `kubectl label namespace default istio-injection=enabled`，然后 `kubectl rollout restart deployment -n default` |
| Prometheus `istio-proxy` job 无 target | RBAC 权限不足 | 确认 prometheus ClusterRole 包含 `pods: get, list, watch` |
| Grafana 面板无数据 | Istio 未安装或 Prometheus 数据源不通 | 检查 Prometheus Targets 页 `istio-proxy` job 是否 UP |
| Selenium `Frontend not accessible` | 端口转发未建立 | 运行 `kubectl port-forward svc/frontend 8081:80` |
| FluxEV `ModuleNotFoundError: No module named 'fluxev'` | PYTHONPATH 未设置 | 设置 `PYTHONPATH=<项目根>/src` |
| istioctl: command not found | Istio 未安装或 PATH 未设置 | 下载 Istio 并添加 `istio-1.22.0/bin` 到 PATH |
