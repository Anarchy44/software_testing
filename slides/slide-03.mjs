import { addBackground, addCard, addFooter, addTopBar, COLORS } from "./common.mjs";

export async function slide03(presentation, ctx) {
  const slide = presentation.slides.add();
  addBackground(slide, ctx);
  addTopBar(slide, ctx, "两篇论文的取舍", "FluxEV 做主复现，Donut 做阅读对照");

  addCard(
    slide,
    ctx,
    54,
    144,
    360,
    418,
    "FluxEV",
    "WSDM 2021\\n\\n关键词：时序异常检测、SPOT、Method of Moments、两步平滑、极值化转换。\\n\\n优点：\\n- 实现短\\n- 不依赖大规模训练\\n- 适合 KPI/监控数据\\n\\n缺点：\\n- 需要自己拼一个轻量版本\\n- 结果更像工程复现而不是学术完全复现",
    COLORS.blue,
  );
  addCard(
    slide,
    ctx,
    454,
    144,
    360,
    418,
    "Donut",
    "WWW 2018\\n\\n关键词：VAE、modified ELBO、missing data injection、MCMC imputation。\\n\\n优点：\\n- 论文经典\\n- 适合做阅读分析\\n- 和 KPI 场景贴合\\n\\n缺点：\\n- 训练链路长\\n- 复现成本高\\n- 对参数和数据质量更敏感",
    COLORS.teal,
  );
  addCard(
    slide,
    ctx,
    854,
    144,
    372,
    418,
    "最终决策",
    "主复现选 FluxEV。\\n理由只有一个：最低标准下，最稳的方案应该先把实验跑出来，再把故事讲清楚。\\n\\nDonut 只保留在论文阅读部分，避免把时间耗在深度模型调参上。",
    COLORS.orange,
  );

  ctx.addShape(slide, {
    x: 108,
    y: 590,
    w: 1060,
    h: 1,
    fill: COLORS.line,
    line: ctx.line(COLORS.line, 0),
  });
  ctx.addText(slide, {
    text: "复现复杂度对比",
    x: 106,
    y: 606,
    w: 200,
    h: 18,
    fontSize: 13,
    bold: true,
    color: COLORS.ink,
  });
  ctx.addText(slide, {
    text: "FluxEV 低 | Donut 中高",
    x: 310,
    y: 606,
    w: 300,
    h: 18,
    fontSize: 13,
    color: COLORS.muted,
  });

  addFooter(slide, ctx, "P3 / 论文选择");
  return slide;
}
