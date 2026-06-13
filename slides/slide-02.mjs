import { addBackground, addCard, addFooter, addPill, addTopBar, COLORS } from "./common.mjs";

export async function slide02(presentation, ctx) {
  const slide = presentation.slides.add();
  addBackground(slide, ctx);
  addTopBar(slide, ctx, "要求拆解", "按最低标准把任务压缩成可交付的四步链路");

  addCard(
    slide,
    ctx,
    56,
    146,
    360,
    170,
    "评分档位",
    "第一档只做 SockShop。\\n第二档换更复杂的开源微服务系统。\\n第三档在第二档基础上再做 1-2 个微服务开发。",
    COLORS.blue,
  );
  addCard(
    slide,
    ctx,
    456,
    146,
    360,
    170,
    "本次选择",
    "用 Online Boutique 代替 SockShop，保留“部署 + 监控 + 测试”的主线。\\n再新增一个轻量 diagnosis-service，满足第三档。",
    COLORS.teal,
  );
  addCard(
    slide,
    ctx,
    856,
    146,
    360,
    170,
    "论文策略",
    "FluxEV 作为主复现，原因是统计型、轻量、实现成本低。\\nDonut 只做阅读与对比，不做完整复现。",
    COLORS.orange,
  );

  ctx.addText(slide, {
    text: "执行路线",
    x: 56,
    y: 354,
    w: 160,
    h: 24,
    fontSize: 18,
    bold: true,
    color: COLORS.ink,
  });
  const steps = [
    ["1", "部署 Online Boutique", COLORS.blue],
    ["2", "接入 Prometheus/Grafana", COLORS.teal],
    ["3", "JMeter / Selenium / ChaosMesh", COLORS.orange],
    ["4", "FluxEV 异常检测 + diagnosis-service", COLORS.green],
  ];
  let x = 56;
  steps.forEach(([num, label, accent], idx) => {
    const w = idx < 3 ? 270 : 302;
    addPill(slide, ctx, x, 398, 46, num, accent);
    ctx.addShape(slide, {
      x: x + 46,
      y: 411,
      w: w - 46,
      h: 4,
      fill: accent,
      line: ctx.line(accent, 0),
    });
    ctx.addText(slide, {
      text: label,
      x: x + 56,
      y: 384,
      w: w - 64,
      h: 34,
      fontSize: 14,
      bold: true,
      color: COLORS.ink,
      valign: "middle",
    });
    x += idx < 3 ? 288 : 0;
  });

  addCard(
    slide,
    ctx,
    56,
    468,
    516,
    156,
    "报告里只保留的内容",
    "部署截图、测试截图、实验图、论文对比、微服务接口说明、仓库链接。\\n不做加分项，不追求复杂算法，不额外扩展更多论文。",
    COLORS.red,
  );
  addCard(
    slide,
    ctx,
    612,
    468,
    604,
    156,
    "交付判断",
    "只要代码能跑、图能出、报告能说清楚、PPT 能讲明白，\\n就已经达到本次作业的最低完成线。",
    COLORS.green,
  );

  addFooter(slide, ctx, "P2 / 要求与实现策略");
  return slide;
}
