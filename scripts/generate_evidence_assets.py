from __future__ import annotations

import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "screenshots"


def run_text(cmd: list[str]) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    text = result.stdout.strip()
    if result.stderr.strip():
        text += ("\n" if text else "") + result.stderr.strip()
    return text or "(no output)"


def font(size: int, mono: bool = False):
    candidates = [
        "C:/Windows/Fonts/consola.ttf" if mono else "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf" if not mono else "C:/Windows/Fonts/consola.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def wrap_text(draw: ImageDraw.ImageDraw, text: str, fnt, max_width: int) -> list[str]:
    lines: list[str] = []
    for raw in text.splitlines():
        if not raw:
          lines.append("")
          continue
        current = ""
        for word in raw.split(" "):
            candidate = word if not current else current + " " + word
            if draw.textbbox((0, 0), candidate, font=fnt)[2] <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
    return lines


def render_terminal_png(title: str, text: str, path: Path, size=(1400, 760)) -> None:
    img = Image.new("RGB", size, "#0B1020")
    draw = ImageDraw.Draw(img)
    title_font = font(24)
    mono = font(20, mono=True)
    small = font(16, mono=True)
    draw.rectangle((0, 0, size[0], 56), fill="#111827")
    draw.text((20, 14), title, fill="#E5E7EB", font=title_font)
    y = 82
    for line in wrap_text(draw, text, mono, size[0] - 80):
        draw.text((28, y), line, fill="#D1FAE5", font=small)
        y += 28
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)


def render_requirements_map(path: Path) -> None:
    img = Image.new("RGB", (1400, 720), "#F8FAFC")
    draw = ImageDraw.Draw(img)
    title_font = font(30)
    body = font(18)
    draw.text((54, 38), "大作业要求拆解图", fill="#0F172A", font=title_font)
    boxes = [
        (70, 150, 280, 140, "#2563EB", "阶段一\\n部署微服务 + 读论文"),
        (390, 150, 280, 140, "#0F766E", "阶段二\\nPrometheus / Grafana / ChaosMesh"),
        (710, 150, 280, 140, "#D97706", "阶段三\\nSelenium / JMeter"),
        (1030, 150, 280, 140, "#15803D", "阶段四\\n论文算法复现"),
    ]
    for x, y, w, h, c, t in boxes:
        draw.rounded_rectangle((x, y, x + w, y + h), radius=16, fill="#FFFFFF", outline="#CBD5E1", width=2)
        draw.rectangle((x, y, x + 10, y + h), fill=c)
        draw.multiline_text((x + 30, y + 36), t, fill="#0F172A", font=body, spacing=8)
    arrows = [(350, 220), (670, 220), (990, 220)]
    for x, y in arrows:
        draw.line((x, y, x + 40, y), fill="#64748B", width=5)
        draw.polygon([(x + 40, y), (x + 26, y - 10), (x + 26, y + 10)], fill="#64748B")
    footer = "三档最低标准路径：选择更复杂的微服务系统 + 完成 1 个微服务开发 + 不做加分项"
    draw.text((72, 380), footer, fill="#334155", font=body)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)


def render_architecture(path: Path) -> None:
    img = Image.new("RGB", (1400, 720), "#FFFFFF")
    draw = ImageDraw.Draw(img)
    title_font = font(30)
    label = font(18)
    small = font(16)
    draw.text((50, 38), "项目架构图", fill="#0F172A", font=title_font)
    nodes = [
        (70, 170, 240, 110, "#2563EB", "Online Boutique"),
        (350, 170, 240, 110, "#0F766E", "Prometheus / Grafana"),
        (630, 170, 240, 110, "#D97706", "FluxEV"),
        (910, 170, 240, 110, "#15803D", "diagnosis-service"),
    ]
    for x, y, w, h, c, t in nodes:
        draw.rounded_rectangle((x, y, x + w, y + h), radius=18, fill="#F8FAFC", outline=c, width=3)
        draw.text((x + 22, y + 38), t, fill="#0F172A", font=label)
    for x in [310, 590, 870]:
        draw.line((x, 225, x + 40, 225), fill="#64748B", width=5)
        draw.polygon([(x + 40, 225), (x + 28, 215), (x + 28, 235)], fill="#64748B")
    draw.text((90, 370), "测试层: JMeter / Selenium / ChaosMesh", fill="#334155", font=small)
    draw.text((90, 410), "数据层: p95 latency, 请求次数, 异常标签", fill="#334155", font=small)
    draw.text((90, 450), "输出层: CSV + 图表 + 查询接口", fill="#334155", font=small)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    render_terminal_png("docker info", run_text(["docker", "info", "--format", "{{.ServerVersion}} {{.OSType}} {{.Architecture}}"]), OUT / "docker_info.png")
    render_terminal_png("minikube status", run_text(["minikube", "status"]), OUT / "minikube_status.png")
    render_terminal_png(
        "source package status",
        "submission-package\nsource code, experiment data, screenshots, report and PPT are included\n.git, node_modules, local caches and absolute host paths are excluded",
        OUT / "git_status.png",
    )
    render_terminal_png("experiment summary", (ROOT / "outputs" / "experiment_summary.json").read_text(encoding="utf-8"), OUT / "experiment_summary.png")
    render_requirements_map(OUT / "requirements_map.png")
    render_architecture(OUT / "architecture.png")
    print(f"wrote screenshots to {OUT}")


if __name__ == "__main__":
    main()
