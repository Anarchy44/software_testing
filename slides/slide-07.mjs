import path from "node:path";
import { addBackground, addFooter, addImageBox, addTopBar, COLORS } from "./common.mjs";

export async function slide07(presentation, ctx) {
  const slide = presentation.slides.add();
  addBackground(slide, ctx);
  addTopBar(slide, ctx, "过程截图与命令结果", "用最少的证据支撑报告和答辩");

  const shots = [
    ["docker_info.png", "Docker daemon", COLORS.blue],
    ["minikube_status.png", "Minikube 状态", COLORS.teal],
    ["git_status.png", "源码包状态", COLORS.orange],
  ];
  const shotDir = path.join(ctx.workspaceDir, "outputs", "screenshots");
  const startX = 58;
  for (const [index, [file, title, accent]] of shots.entries()) {
    await addImageBox(
      slide,
      ctx,
      path.join(shotDir, file),
      startX + index * 390,
      154,
      360,
      424,
      title,
    );
    ctx.addShape(slide, {
      x: startX + index * 390,
      y: 154,
      w: 360,
      h: 34,
      fill: accent,
      line: ctx.line(accent, 0),
    });
    ctx.addText(slide, {
      text: title,
      x: startX + index * 390 + 14,
      y: 162,
      w: 250,
      h: 16,
      fontSize: 13,
      bold: true,
      color: COLORS.white,
    });
  }

  ctx.addShape(slide, {
    x: 56,
    y: 606,
    w: 1168,
    h: 50,
    fill: COLORS.white,
    line: ctx.line(COLORS.line, 1),
  });
  ctx.addShape(slide, {
    x: 56,
    y: 606,
    w: 6,
    h: 50,
    fill: COLORS.green,
    line: ctx.line(COLORS.green, 0),
  });
  ctx.addText(slide, {
    text: "这些截图会写进报告附录，也会放进 PPT 的证据页，用来证明环境确实拉起过、命令确实执行过。",
    x: 76,
    y: 618,
    w: 1120,
    h: 20,
    fontSize: 13,
    color: COLORS.muted,
  });

  addFooter(slide, ctx, "P7 / 过程证据");
  return slide;
}
