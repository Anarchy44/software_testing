export const COLORS = {
  bg: "#F6F8FB",
  ink: "#0F172A",
  muted: "#475569",
  line: "#D9E0EA",
  blue: "#2563EB",
  teal: "#0F766E",
  orange: "#D97706",
  green: "#15803D",
  red: "#B91C1C",
  white: "#FFFFFF",
};

export function addBackground(slide, ctx, color = COLORS.bg) {
  ctx.addShape(slide, {
    x: 0,
    y: 0,
    w: ctx.W,
    h: ctx.H,
    fill: color,
    line: ctx.line(color, 0),
  });
}

export function addTopBar(slide, ctx, title, subtitle, accent = COLORS.blue) {
  ctx.addShape(slide, {
    x: 0,
    y: 0,
    w: ctx.W,
    h: 14,
    fill: accent,
    line: ctx.line(accent, 0),
  });
  ctx.addText(slide, {
    text: title,
    x: 56,
    y: 42,
    w: 820,
    h: 54,
    fontSize: 30,
    bold: true,
    color: COLORS.ink,
    typeface: ctx.fonts.title,
  });
  if (subtitle) {
    ctx.addText(slide, {
      text: subtitle,
      x: 58,
      y: 88,
      w: 900,
      h: 34,
      fontSize: 14,
      color: COLORS.muted,
      typeface: ctx.fonts.body,
    });
  }
}

export function addFooter(slide, ctx, pageText) {
  ctx.addShape(slide, {
    x: 48,
    y: ctx.H - 34,
    w: ctx.W - 96,
    h: 1,
    fill: COLORS.line,
    line: ctx.line(COLORS.line, 0),
  });
  ctx.addText(slide, {
    text: pageText,
    x: 56,
    y: ctx.H - 28,
    w: 360,
    h: 18,
    fontSize: 11,
    color: COLORS.muted,
  });
  ctx.addText(slide, {
    text: "Software Testing and Maintenance Final Project",
    x: ctx.W - 390,
    y: ctx.H - 28,
    w: 330,
    h: 18,
    fontSize: 11,
    color: COLORS.muted,
    align: "right",
  });
}

export function addCard(slide, ctx, x, y, w, h, title, body, accent = COLORS.blue) {
  ctx.addShape(slide, {
    x,
    y,
    w,
    h,
    fill: COLORS.white,
    line: ctx.line(COLORS.line, 1),
  });
  ctx.addShape(slide, {
    x,
    y,
    w: 6,
    h,
    fill: accent,
    line: ctx.line(accent, 0),
  });
  if (title) {
    ctx.addText(slide, {
      text: title,
      x: x + 18,
      y: y + 14,
      w: w - 28,
      h: 26,
      fontSize: 18,
      bold: true,
      color: COLORS.ink,
      typeface: ctx.fonts.body,
    });
  }
  if (body) {
    ctx.addText(slide, {
      text: body,
      x: x + 18,
      y: y + 46,
      w: w - 28,
      h: h - 58,
      fontSize: 13,
      color: COLORS.muted,
      typeface: ctx.fonts.body,
      valign: "top",
    });
  }
}

export function addPill(slide, ctx, x, y, w, text, accent = COLORS.blue, invert = false) {
  ctx.addShape(slide, {
    x,
    y,
    w,
    h: 30,
    fill: invert ? COLORS.white : accent,
    line: ctx.line(accent, 1),
  });
  ctx.addText(slide, {
    text,
    x: x + 10,
    y: y + 6,
    w: w - 20,
    h: 18,
    fontSize: 11,
    color: invert ? accent : COLORS.white,
    bold: true,
    align: "center",
  });
}

export async function addImageBox(slide, ctx, imagePath, x, y, w, h, label) {
  ctx.addShape(slide, {
    x,
    y,
    w,
    h,
    fill: COLORS.white,
    line: ctx.line(COLORS.line, 1),
  });
  await ctx.addImage(slide, {
    path: imagePath,
    x: x + 10,
    y: y + 10,
    w: w - 20,
    h: h - 20,
    fit: "contain",
    alt: label,
  });
  if (label) {
    ctx.addText(slide, {
      text: label,
      x: x + 12,
      y: y + h - 24,
      w: w - 24,
      h: 16,
      fontSize: 10,
      color: COLORS.muted,
      align: "right",
    });
  }
}

export function addSmallLabel(slide, ctx, x, y, text, accent = COLORS.blue) {
  ctx.addText(slide, {
    text,
    x,
    y,
    w: 220,
    h: 18,
    fontSize: 11,
    bold: true,
    color: accent,
  });
}
