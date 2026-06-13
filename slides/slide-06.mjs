import { addBackground, addCard, addFooter, addTopBar, COLORS } from "./common.mjs";

export async function slide06(presentation, ctx) {
  const slide = presentation.slides.add();
  addBackground(slide, ctx);
  addTopBar(slide, ctx, "新增微服务：diagnosis-service", "第三档最低成本开发点，只做结果查询，不做复杂业务");

  addCard(
    slide,
    ctx,
    58,
    150,
    360,
    164,
    "接口",
    "/health: 健康检查\\n/summary: 异常统计\\n/anomalies?limit=20: 返回异常点列表",
    COLORS.blue,
  );
  addCard(
    slide,
    ctx,
    458,
    150,
    360,
    164,
    "数据",
    "读取 metrics_with_scores.csv。\\n输入来自 FluxEV 复现实验输出。\\n这样报告里能说清楚“算法结果如何暴露给系统”。",
    COLORS.teal,
  );
  addCard(
    slide,
    ctx,
    858,
    150,
    364,
    164,
    "部署",
    "Deployment + Service + ConfigMap。\\n挂载实验结果文件，端口 8080。\\n这就是本次最小微服务开发。",
    COLORS.orange,
  );

  ctx.addShape(slide, {
    x: 84,
    y: 362,
    w: 1084,
    h: 170,
    fill: COLORS.white,
    line: ctx.line(COLORS.line, 1),
  });
  ctx.addText(slide, {
    text: "请求示意",
    x: 106,
    y: 382,
    w: 120,
    h: 22,
    fontSize: 16,
    bold: true,
    color: COLORS.ink,
  });
  ctx.addText(slide, {
    text: "curl http://diagnosis-service/summary\\n→ { points, predicted_anomalies, threshold, metric }",
    x: 106,
    y: 422,
    w: 520,
    h: 76,
    fontSize: 18,
    color: COLORS.muted,
  });
  ctx.addText(slide, {
    text: "这个服务的作用不是替代业务，而是把实验结果变成一个可查、可演示、可截图的接口。",
    x: 650,
    y: 414,
    w: 462,
    h: 84,
    fontSize: 15,
    color: COLORS.ink,
  });

  addFooter(slide, ctx, "P6 / 微服务开发");
  return slide;
}
