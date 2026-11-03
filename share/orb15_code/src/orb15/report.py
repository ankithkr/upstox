"""Tiny HTML/SVG helpers for the ORB-15 report (no third-party deps)."""
import html

CSS = """
:root{--bg:#fff;--fg:#1c2330;--mut:#667085;--line:#e4e7ec;--card:#f8f9fb;--acc:#2563eb;--pos:#15803d;--neg:#b42318;--warn:#fff6e0;--warnb:#f5c46b}
@media(prefers-color-scheme:dark){:root{--bg:#10141c;--fg:#e6e9ef;--mut:#98a2b3;--line:#2a3140;--card:#171c26;--acc:#6ea0ff;--pos:#4ade80;--neg:#f87171;--warn:#2a2310;--warnb:#7a5d1d}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 system-ui,Segoe UI,sans-serif}
main{max-width:1060px;margin:0 auto;padding:24px 16px 80px}
h1{font-size:26px;margin:0 0 4px}h2{font-size:20px;margin:40px 0 8px;padding-top:16px;border-top:1px solid var(--line)}h3{font-size:16px;margin:24px 0 6px}
p,li{max-width:80ch}.mut{color:var(--mut)}code{background:var(--card);padding:1px 5px;border-radius:4px;font-size:13px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:14px 0}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px}.kpi b{display:block;font-size:22px}.kpi span{color:var(--mut);font-size:12px}
.box{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 16px;margin:14px 0}
.warn{background:var(--warn);border-color:var(--warnb)}
.tw{overflow-x:auto;margin:8px 0}table{border-collapse:collapse;font-size:13px;font-variant-numeric:tabular-nums;min-width:100%}
th,td{padding:5px 9px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}th:first-child,td:first-child{text-align:left}
th{color:var(--mut);font-weight:600;position:sticky;top:0;background:var(--bg)}tr.hl td{background:var(--card);font-weight:600}
.pos{color:var(--pos)}.neg{color:var(--neg)}svg{max-width:100%;height:auto;display:block}svg text{fill:var(--mut);font-size:11px}
.legend{font-size:12px;color:var(--mut);margin:2px 0 10px}.legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin:0 4px 0 12px;vertical-align:middle}
"""


def esc(x):
    return html.escape(str(x))


def cls(v, eps=0.0):
    return "pos" if v > eps else ("neg" if v < -eps else "")


def table(headers, rows, hl=None, heat_cols=(), heat_scale=1.0):
    """rows: list of lists of (display_str, raw_number|None) or plain str. heat_cols: column idx tinted by raw."""
    out = ["<div class='tw'><table><tr>" + "".join(f"<th>{esc(h)}</th>" for h in headers) + "</tr>"]
    for ri, row in enumerate(rows):
        tr = "<tr class='hl'>" if hl is not None and ri == hl else "<tr>"
        cells = []
        for ci, cell in enumerate(row):
            disp, raw = cell if isinstance(cell, tuple) else (cell, None)
            style = ""
            if raw is not None and ci in heat_cols:
                a = max(-1.0, min(1.0, raw / heat_scale))
                col = "21,128,61" if a > 0 else "180,35,24"
                style = f" style='background:rgba({col},{abs(a) * 0.35:.2f})'"
            c = f" class='{cls(raw)}'" if raw is not None and ci not in heat_cols and ci > 0 else ""
            cells.append(f"<td{style}{c}>{esc(disp)}</td>")
        out.append(tr + "".join(cells) + "</tr>")
    out.append("</table></div>")
    return "".join(out)


PALETTE = ["#2563eb", "#dc6803", "#12a594", "#9333ea", "#b42318", "#667085"]


def svg_lines(series, labels_x=None, w=900, h=260, ylabel="", zero=True):
    """series: list of (name, [y...]) sharing the same x positions."""
    pl, pr, pt, pb = 56, 12, 10, 26
    n = max(len(s[1]) for s in series)
    ys = [v for _, s in series for v in s]
    lo, hi = min(ys + ([0] if zero else [])), max(ys + ([0] if zero else []))
    if hi == lo:
        hi = lo + 1
    sx = lambda i: pl + (w - pl - pr) * i / max(n - 1, 1)
    sy = lambda v: pt + (h - pt - pb) * (1 - (v - lo) / (hi - lo))
    g = [f"<svg viewBox='0 0 {w} {h}' role='img'>"]
    for k in range(5):
        v = lo + (hi - lo) * k / 4
        g.append(f"<line x1='{pl}' x2='{w - pr}' y1='{sy(v):.1f}' y2='{sy(v):.1f}' stroke='currentColor' opacity='.12'/>")
        g.append(f"<text x='{pl - 6}' y='{sy(v) + 4:.1f}' text-anchor='end'>{v:,.0f}</text>")
    if zero:
        g.append(f"<line x1='{pl}' x2='{w - pr}' y1='{sy(0):.1f}' y2='{sy(0):.1f}' stroke='currentColor' opacity='.45'/>")
    if labels_x:
        step = max(1, len(labels_x) // 8)
        for i in range(0, len(labels_x), step):
            g.append(f"<text x='{sx(i):.1f}' y='{h - 8}' text-anchor='middle'>{esc(labels_x[i])}</text>")
    for si, (name, s) in enumerate(series):
        pts = " ".join(f"{sx(i):.1f},{sy(v):.1f}" for i, v in enumerate(s))
        g.append(f"<polyline fill='none' stroke='{PALETTE[si % 6]}' stroke-width='1.8' points='{pts}'/>")
    g.append("</svg>")
    leg = "<div class='legend'>" + "".join(
        f"<i style='background:{PALETTE[i % 6]}'></i>{esc(n_)}" for i, (n_, _) in enumerate(series)) + (
        f" &nbsp; <span>{esc(ylabel)}</span>" if ylabel else "") + "</div>"
    return "".join(g) + leg


def svg_bars(labels, values, w=900, h=220, fmt="{:.0f}", color=None):
    pl, pr, pt, pb = 50, 12, 14, 34
    lo, hi = min(values + [0]), max(values + [0])
    if hi == lo:
        hi = lo + 1
    bw = (w - pl - pr) / len(values)
    sy = lambda v: pt + (h - pt - pb) * (1 - (v - lo) / (hi - lo))
    g = [f"<svg viewBox='0 0 {w} {h}' role='img'>",
         f"<line x1='{pl}' x2='{w - pr}' y1='{sy(0):.1f}' y2='{sy(0):.1f}' stroke='currentColor' opacity='.45'/>"]
    for i, (lab, v) in enumerate(zip(labels, values)):
        x = pl + i * bw + bw * 0.15
        y0, y1 = sy(max(v, 0)), sy(min(v, 0))
        c = color or ("#15803d" if v >= 0 else "#b42318")
        g.append(f"<rect x='{x:.1f}' y='{y0:.1f}' width='{bw * 0.7:.1f}' height='{max(y1 - y0, 1):.1f}' fill='{c}' opacity='.85'/>")
        g.append(f"<text x='{x + bw * 0.35:.1f}' y='{(y0 - 3) if v >= 0 else (y1 + 11):.1f}' text-anchor='middle'>{fmt.format(v)}</text>")
        g.append(f"<text x='{x + bw * 0.35:.1f}' y='{h - 14}' text-anchor='middle'>{esc(lab)}</text>")
    g.append("</svg>")
    return "".join(g)
