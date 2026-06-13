import fs from "node:fs/promises";
import path from "node:path";
import { addBackground, addFooter, addImageBox, addTopBar, COLORS } from "./common.mjs";

export async function slide05(presentation, ctx) {
  const slide = presentation.slides.add();
  addBackground(slide, ctx);
  addTopBar(slide, ctx, "FluxEV 复现实验结果", "先跑出图，再谈效果；这是最低标准最重要的一步");

  const summaryPath = path.join(ctx.workspaceDir, "outputs", "experiment_summary.json");
  const summary = JSON.parse(await fs.readFile(summaryPath, "utf8"));

  ctx.addShape(slide, {
    x: 58,
    y: 146,
    w: 348,
    h: 112,
    fill: COLORS.white,
    line: ctx.line(COLORS.line, 1),
  });
  ctx.addText(slide, {
    text: "Precision",
    x: 78,
    y: 164,
    w: 120,
    h: 18,
    fontSize: 12,
    color: COLORS.muted,
  });
  ctx.addText(slide, {
    text: `${summary.precision.toFixed(3)}`,
    x: 78,
    y: 186,
    w: 120,
    h: 40,
    fontSize: 28,
    bold: true,
    color: COLORS.blue,
  });
  ctx.addText(slide, {
    text: "Recall",
    x: 198,
    y: 164,
    w: 90,
    h: 18,
    fontSize: 12,
    color: COLORS.muted,
  });
  ctx.addText(slide, {
    text: `${summary.recall.toFixed(3)}`,
    x: 198,
    y: 186,
    w: 90,
    h: 40,
    fontSize: 28,
    bold: true,
    color: COLORS.teal,
  });
  ctx.addText(slide, {
    text: "F1",
    x: 300,
    y: 164,
    w: 70,
    h: 18,
    fontSize: 12,
    color: COLORS.muted,
  });
  ctx.addText(slide, {
    text: `${summary.f1.toFixed(3)}`,
    x: 300,
    y: 186,
    w: 80,
    h: 40,
    fontSize: 28,
    bold: true,
    color: COLORS.orange,
  });

  await addImageBox(
    slide,
    ctx,
    path.join(ctx.workspaceDir, "outputs", "figures", "fluxev_detection_result.png"),
    58,
    286,
    572,
    338,
    "detection",
  );
  await addImageBox(
    slide,
    ctx,
    path.join(ctx.workspaceDir, "outputs", "figures", "fluxev_score_threshold.png"),
    662,
    286,
    562,
    338,
    "threshold",
  );

  addFooter(slide, ctx, "P5 / 复现结果");
  return slide;
}
