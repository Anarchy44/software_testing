import { addBackground, addFooter, addPill, COLORS } from "./common.mjs";

export async function slide01(presentation, ctx) {
  const slide = presentation.slides.add();
  addBackground(slide, ctx, COLORS.bg);

  ctx.addText(slide, {
    text: "软件测试与维护大作业",
    x: 58,
    y: 130,
    w: 760,
    h: 68,
    fontSize: 38,
    bold: true,
    color: COLORS.ink,
    typeface: ctx.fonts.title,
  });
  ctx.addText(slide, {
    text: "第三档最低标准路线：Online Boutique + diagnosis-service + FluxEV 复现",
    x: 60,
    y: 204,
    w: 820,
    h: 34,
    fontSize: 17,
    color: COLORS.muted,
  });
  ctx.addText(slide, {
    text: "论文选择：FluxEV 主复现，Donut 作为对照阅读",
    x: 60,
    y: 248,
    w: 700,
    h: 26,
    fontSize: 15,
    color: COLORS.teal,
    bold: true,
  });

  addPill(slide, ctx, 60, 316, 150, "最低标准", COLORS.blue);
  addPill(slide, ctx, 222, 316, 160, "可运行复现", COLORS.teal);
  addPill(slide, ctx, 394, 316, 178, "过程截图齐备", COLORS.orange);

  ctx.addText(slide, {
    text: "交付物",
    x: 60,
    y: 396,
    w: 120,
    h: 24,
    fontSize: 15,
    bold: true,
    color: COLORS.ink,
  });
  ctx.addText(slide, {
    text: "1. 大作业报告 PDF\\n2. 展示汇报 PPTX\\n3. 源码提交包\\n4. 运行与部署截图",
    x: 60,
    y: 428,
    w: 360,
    h: 112,
    fontSize: 15,
    color: COLORS.muted,
    typeface: ctx.fonts.body,
    valign: "top",
  });

  ctx.addShape(slide, {
    x: 820,
    y: 122,
    w: 370,
    h: 430,
    fill: COLORS.white,
    line: ctx.line(COLORS.line, 1),
  });
  ctx.addText(slide, {
    text: "Project snapshot",
    x: 846,
    y: 148,
    w: 220,
    h: 22,
    fontSize: 15,
    bold: true,
    color: COLORS.ink,
  });
  ctx.addShape(slide, {
    x: 846,
    y: 188,
    w: 318,
    h: 86,
    fill: "#EEF4FF",
    line: ctx.line("#D6E3FF", 1),
  });
  ctx.addText(slide, {
    text: "Online Boutique\\n+\\n新增 diagnosis-service",
    x: 862,
    y: 206,
    w: 286,
    h: 48,
    fontSize: 22,
    bold: true,
    color: COLORS.blue,
    align: "center",
  });
  ctx.addShape(slide, {
    x: 846,
    y: 292,
    w: 318,
    h: 210,
    fill: "#F8FAFC",
    line: ctx.line(COLORS.line, 1),
  });
  ctx.addText(slide, {
    text: "复现主线\\nFluxEV: 轻量时序异常检测\\n\\n展示主线\\nPrometheus + Grafana + ChaosMesh\\n\\n测试主线\\nSelenium + JMeter",
    x: 866,
    y: 318,
    w: 278,
    h: 160,
    fontSize: 16,
    color: COLORS.ink,
    typeface: ctx.fonts.body,
    valign: "top",
  });

  addFooter(slide, ctx, "P1 / 定题与交付物");
  return slide;
}
