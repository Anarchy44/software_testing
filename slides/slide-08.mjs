import { addBackground, addCard, addFooter, addTopBar, COLORS } from "./common.mjs";

export async function slide08(presentation, ctx) {
  const slide = presentation.slides.add();
  addBackground(slide, ctx);
  addTopBar(slide, ctx, "结论与仓库", "完成最低标准第三档，保留扩展空间但不做加分项");

  addCard(
    slide,
    ctx,
    58,
    148,
    350,
    224,
    "完成情况",
    "1. 选题和论文已确定。\\n2. Online Boutique 作为复杂微服务系统。\\n3. diagnosis-service 作为开发点。\\n4. FluxEV 作为主复现。\\n5. 报告、PPT、仓库与截图一套打通。",
    COLORS.blue,
  );
  addCard(
    slide,
    ctx,
    446,
    148,
    350,
    224,
    "不做的部分",
    "不做加分论文对比。\\n不做智能体运维封装。\\n不追求深度学习重复现。\\n目标就是把第三档最低线稳稳落地。",
    COLORS.teal,
  );
  addCard(
    slide,
    ctx,
    834,
    148,
    386,
    224,
    "提交包",
    "源码、实验数据、截图、报告和 PPT 已统一放入项目目录。\\n最终提交时使用脱敏压缩包，不展示个人仓库地址或本机绝对路径。",
    COLORS.orange,
  );

  ctx.addShape(slide, {
    x: 90,
    y: 430,
    w: 1098,
    h: 150,
    fill: "#EFF6FF",
    line: ctx.line("#DBEAFE", 1),
  });
  ctx.addText(slide, {
    text: "答辩时的讲法",
    x: 118,
    y: 456,
    w: 160,
    h: 24,
    fontSize: 18,
    bold: true,
    color: COLORS.blue,
  });
  ctx.addText(slide, {
    text: "先讲系统，再讲测试，再讲监控，最后讲复现。\\n逻辑顺序尽量稳定，别在有限时间里把重点讲散。",
    x: 118,
    y: 494,
    w: 630,
    h: 62,
    fontSize: 16,
    color: COLORS.ink,
  });
  ctx.addText(slide, {
    text: "结束",
    x: 960,
    y: 476,
    w: 140,
    h: 50,
    fontSize: 28,
    bold: true,
    color: COLORS.green,
    align: "center",
  });

  addFooter(slide, ctx, "P8 / 结论");
  return slide;
}
