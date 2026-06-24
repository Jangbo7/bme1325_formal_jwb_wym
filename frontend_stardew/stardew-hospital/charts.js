const PALETTE = [
  "#4f7d4f",
  "#d78c5a",
  "#5f95c9",
  "#d8bb4b",
  "#9b6fb0",
  "#d66f73",
  "#71a2a1",
  "#8a6a3f",
];

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function niceNumber(value) {
  if (!Number.isFinite(value)) return "0";
  return Math.round(value * 10) / 10;
}

function shortLabel(label, max = 10) {
  const text = String(label ?? "");
  if (text.length <= max) return text;
  return `${text.slice(0, max - 1)}…`;
}

export function renderStatCards(cards) {
  return cards.map((card) => `
    <article class="stat-card">
      <span>${escapeHtml(card.label)}</span>
      <strong>${escapeHtml(card.value)}</strong>
      ${card.note ? `<div class="muted">${escapeHtml(card.note)}</div>` : ""}
    </article>
  `).join("");
}

export function renderBarChart({ title, data, width = 920, height = 320 }) {
  const padding = { top: 34, right: 22, bottom: 66, left: 44 };
  const innerWidth = width - padding.left - padding.right;
  const innerHeight = height - padding.top - padding.bottom;
  const maxValue = Math.max(1, ...data.map((item) => Number(item.value) || 0));
  const barWidth = data.length ? innerWidth / data.length : innerWidth;
  const step = Math.max(1, barWidth * 0.18);
  const svgBars = data.map((item, index) => {
    const value = Number(item.value) || 0;
    const barHeight = innerHeight * (value / maxValue);
    const x = padding.left + index * barWidth + step * 0.5;
    const y = padding.top + innerHeight - barHeight;
    const w = Math.max(10, barWidth - step);
    const color = item.color || PALETTE[index % PALETTE.length];
    return `
      <g>
        <rect x="${x.toFixed(2)}" y="${y.toFixed(2)}" width="${w.toFixed(2)}" height="${Math.max(0, barHeight).toFixed(2)}" rx="10" fill="${color}">
          <title>${escapeHtml(item.label)}: ${niceNumber(value)}</title>
        </rect>
        <text x="${(x + w / 2).toFixed(2)}" y="${(y - 8).toFixed(2)}" text-anchor="middle" font-size="12" fill="#3f3527">${niceNumber(value)}</text>
        <text x="${(x + w / 2).toFixed(2)}" y="${height - 18}" text-anchor="middle" font-size="12" fill="#5f5340">${escapeHtml(shortLabel(item.label, 12))}</text>
      </g>
    `;
  }).join("");

  const gridLines = Array.from({ length: 5 }, (_value, index) => {
    const y = padding.top + (innerHeight * index) / 4;
    return `
      <line x1="${padding.left}" y1="${y}" x2="${width - padding.right}" y2="${y}" stroke="rgba(112,80,47,0.12)" stroke-dasharray="4 6" />
      <text x="${padding.left - 10}" y="${y + 4}" text-anchor="end" font-size="11" fill="#766a59">${niceNumber(maxValue - (maxValue * index) / 4)}</text>
    `;
  }).join("");

  return `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(title)}">
      <defs>
        <linearGradient id="barFill" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stop-color="#ffffff" stop-opacity="0.16" />
          <stop offset="100%" stop-color="#000000" stop-opacity="0.12" />
        </linearGradient>
      </defs>
      <rect x="0" y="0" width="${width}" height="${height}" rx="20" fill="rgba(255,255,255,0.35)" />
      ${gridLines}
      ${svgBars}
      <rect x="${padding.left}" y="${padding.top}" width="${innerWidth}" height="${innerHeight}" rx="16" fill="url(#barFill)" fill-opacity="0.12" stroke="rgba(112,80,47,0.12)" />
    </svg>
  `;
}

export function renderPieChart({ title, data, width = 540, height = 320 }) {
  const cx = width / 2;
  const cy = height / 2;
  const radius = Math.min(width, height) * 0.28;
  const total = Math.max(1, data.reduce((sum, item) => sum + (Number(item.value) || 0), 0));
  let startAngle = -Math.PI / 2;

  const paths = data.map((item, index) => {
    const value = Number(item.value) || 0;
    const angle = (value / total) * Math.PI * 2;
    const endAngle = startAngle + angle;
    const x1 = cx + radius * Math.cos(startAngle);
    const y1 = cy + radius * Math.sin(startAngle);
    const x2 = cx + radius * Math.cos(endAngle);
    const y2 = cy + radius * Math.sin(endAngle);
    const largeArc = angle > Math.PI ? 1 : 0;
    const color = item.color || PALETTE[index % PALETTE.length];
    const path = `
      M ${cx} ${cy}
      L ${x1} ${y1}
      A ${radius} ${radius} 0 ${largeArc} 1 ${x2} ${y2}
      Z
    `;
    startAngle = endAngle;
    return `
      <path d="${path}" fill="${color}" stroke="rgba(255,255,255,0.8)" stroke-width="2">
        <title>${escapeHtml(item.label)}: ${niceNumber(value)}</title>
      </path>
    `;
  }).join("");

  const legend = data.map((item, index) => `
    <div class="pill" style="background:${item.color || PALETTE[index % PALETTE.length]};color:#fff">
      ${escapeHtml(item.label)} ${niceNumber(item.value)}
    </div>
  `).join("");

  return `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(title)}">
      <rect x="0" y="0" width="${width}" height="${height}" rx="20" fill="rgba(255,255,255,0.35)" />
      ${paths}
      <circle cx="${cx}" cy="${cy}" r="${radius * 0.48}" fill="rgba(255,248,231,0.98)" stroke="rgba(112,80,47,0.15)" />
      <text x="${cx}" y="${cy - 2}" text-anchor="middle" font-size="14" fill="#4a3d2c" font-weight="700">${escapeHtml(title)}</text>
      <text x="${cx}" y="${cy + 18}" text-anchor="middle" font-size="12" fill="#6f5f47">${niceNumber(total)} total</text>
    </svg>
    <div class="legend-row">${legend}</div>
  `;
}

export function renderLineChart({ title, series, width = 920, height = 320 }) {
  const padding = { top: 28, right: 20, bottom: 42, left: 46 };
  const innerWidth = width - padding.left - padding.right;
  const innerHeight = height - padding.top - padding.bottom;
  const maxPoints = Math.max(1, ...series.map((s) => s.values.length));
  const combinedMax = Math.max(1, ...series.flatMap((s) => s.values.map((value) => Number(value) || 0)));
  const xScale = (index) => padding.left + (index / Math.max(1, maxPoints - 1)) * innerWidth;
  const yScale = (value) => padding.top + innerHeight - (Math.max(0, Number(value) || 0) / combinedMax) * innerHeight;

  const gridLines = Array.from({ length: 5 }, (_value, index) => {
    const y = padding.top + (innerHeight * index) / 4;
    return `
      <line x1="${padding.left}" y1="${y}" x2="${width - padding.right}" y2="${y}" stroke="rgba(112,80,47,0.12)" stroke-dasharray="4 6" />
      <text x="${padding.left - 10}" y="${y + 4}" text-anchor="end" font-size="11" fill="#766a59">${niceNumber(combinedMax - (combinedMax * index) / 4)}</text>
    `;
  }).join("");

  const linePaths = series.map((item, index) => {
    const color = item.color || PALETTE[index % PALETTE.length];
    const points = item.values.map((value, pointIndex) => `${xScale(pointIndex).toFixed(2)},${yScale(value).toFixed(2)}`);
    const path = points.length ? `M ${points.join(" L ")}` : "";
    return `
      <path d="${path}" fill="none" stroke="${color}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" />
      ${item.values.map((value, pointIndex) => `
        <circle cx="${xScale(pointIndex)}" cy="${yScale(value)}" r="4.5" fill="${color}">
          <title>${escapeHtml(item.name)}: ${niceNumber(value)}</title>
        </circle>
      `).join("")}
    `;
  }).join("");

  const legend = series.map((item, index) => `
    <div class="pill" style="background:${item.color || PALETTE[index % PALETTE.length]};color:#fff">
      ${escapeHtml(item.name)}
    </div>
  `).join("");

  return `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(title)}">
      <rect x="0" y="0" width="${width}" height="${height}" rx="20" fill="rgba(255,255,255,0.35)" />
      ${gridLines}
      ${linePaths}
      <text x="${padding.left}" y="${18}" font-size="12" fill="#6f5f47">${escapeHtml(title)}</text>
      ${Array.from({ length: maxPoints }, (_value, index) => {
        const label = String(index + 1);
        const x = xScale(index);
        return `<text x="${x}" y="${height - 18}" text-anchor="middle" font-size="11" fill="#6f5f47">${label}</text>`;
      }).join("")}
    </svg>
    <div class="legend-row">${legend}</div>
  `;
}

export { escapeHtml, PALETTE };
