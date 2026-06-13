import { addBackground, addCard, addFooter, addPill, addTopBar, COLORS } from "./common.mjs";

export async function slide04(presentation, ctx) {
  const slide = presentation.slides.add();
  addBackground(slide, ctx);
  addTopBar(slide, ctx, "系统与数据链路", "从微服务监控数据到异常检测输出，再回到诊断服务");

  const boxes = [
    [58, 166, 250, 92, "Online Boutique", "微服务系统", COLORS.blue],
    [348, 166, 250, 92, "Prometheus", "采集指标", COLORS.teal],
    [638, 166, 250, 92, "FluxEV", "复现算法", COLORS.orange],
    [928, 166, 250, 92, "diagnosis-service", "查询接口", COLORS.green],
  ];
  boxes.forEach(([x, y, w, h, title, sub, accent]) => {
    addCard(slide, ctx, x, y, w, h, title, sub, accent);
  });
  [288, 578, 868].forEach((x) => {
    ctx.addText(slide, {
      text: "→",
      x,
      y: 188,
      w: 30,
      h: 28,
      fontSize: 24,
      bold: true,
      color: COLORS.muted,
      align: "center",
    });
  });

  addCard(
    slide,
    ctx,
    58,
    310,
    350,
    176,
    "测试工具",
    "JMeter：并发与性能压测。\\nSelenium：前端功能测试。\\nChaosMesh：故障注入。\\nGrafana：监控与可视化。",
    COLORS.blue,
  );
  addCard(
    slide,
    ctx,
    448,
    310,
    350,
    176,
    "复现数据",
    "用 p95 latency 这类 KPI 风格指标构造时序。\\n保留周期性、噪声和突发异常，方便说明 FluxEV 的工作方式。",
    COLORS.teal,
  );
  addCard(
    slide,
    ctx,
    838,
    310,
    350,
    176,
    "开发部分",
    "新增 diagnosis-service：\\n/health、/summary、/anomalies。\\n它负责把复现后的结果转成简单的查询接口。",
    COLORS.orange,
  );

  addPill(slide, ctx, 60, 528, 132, "输出", COLORS.green);
  ctx.addText(slide, {
    text: "异常分数、阈值、预测标签、实验图、报告图表、PPT 插图",
    x: 208,
    y: 531,
    w: 870,
    h: 24,
    fontSize: 14,
    color: COLORS.muted,
  });

  addFooter(slide, ctx, "P4 / 架构与数据链路");
  return slide;
}
