import csv
import html
import math
import pathlib


def _safe_float(x, default=None):
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default


def _svg_line(points, width, height, pad=24, stroke="#22c55e"):
    if not points:
        return ""
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    x_min = min(xs)
    x_max = max(xs)
    y_min = min(ys)
    y_max = max(ys)
    if x_max == x_min:
        x_max = x_min + 1
    if y_max == y_min:
        y_max = y_min + 1

    def sx(x):
        return pad + (x - x_min) / (x_max - x_min) * (width - 2 * pad)

    def sy(y):
        return height - pad - (y - y_min) / (y_max - y_min) * (height - 2 * pad)

    path = []
    for i, (x, y) in enumerate(points):
        cmd = "M" if i == 0 else "L"
        path.append(f"{cmd}{sx(x):.2f},{sy(y):.2f}")

    axes = f"<rect x='{pad}' y='{pad}' width='{width-2*pad}' height='{height-2*pad}' fill='none' stroke='#334155' stroke-width='1'/>"
    line = f"<path d='{''.join(path)}' fill='none' stroke='{stroke}' stroke-width='2'/>"

    return f"<svg width='{width}' height='{height}' viewBox='0 0 {width} {height}' xmlns='http://www.w3.org/2000/svg'>{axes}{line}</svg>"


def write_report(csv_path, out_path=None, title="Run report"):
    csv_path = pathlib.Path(csv_path)
    if out_path is None:
        out_path = csv_path.with_suffix(".html")
    out_path = pathlib.Path(out_path)

    rows = []
    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)

    combined = []
    for r in rows:
        tag = (r.get("tag") or "").strip()
        if tag in ("single", "combined"):
            score = _safe_float(r.get("score"), None)
            idx = _safe_float(r.get("idx"), None)
            if score is None or idx is None or not math.isfinite(score):
                continue
            combined.append((int(idx), float(score), r))

    combined.sort(key=lambda x: x[0])

    best = max(combined, key=lambda x: x[1])[2] if combined else None
    top = sorted(combined, key=lambda x: x[1], reverse=True)[:10]

    chart = _svg_line([(i, s) for i, s, _ in combined], 900, 260)

    def td(s):
        return f"<td>{html.escape(str(s))}</td>"

    table_rows = []
    for _, s, r in top:
        table_rows.append(
            "<tr>"
            + td(r.get("idx"))
            + td(f"{s:.4f}")
            + td(r.get("outputDpi"))
            + td(r.get("syncSpeed"))
            + td(r.get("motivity"))
            + td(r.get("gamma"))
            + td(r.get("smooth"))
            + "</tr>"
        )

    summary = ""
    if best is not None:
        summary = (
            f"<p><b>Best</b> score={html.escape(best.get('score',''))} "
            f"DPI={html.escape(best.get('outputDpi',''))} syncSpeed={html.escape(best.get('syncSpeed',''))} "
            f"motivity={html.escape(best.get('motivity',''))} gamma={html.escape(best.get('gamma',''))} smooth={html.escape(best.get('smooth',''))}</p>"
        )

    body = f"""
<!doctype html>
<html>
<head>
<meta charset='utf-8'/>
<title>{html.escape(title)}</title>
<style>
body {{ font-family: Segoe UI, Arial, sans-serif; background: #0b0f14; color: #e5e7eb; margin: 24px; }}
a {{ color: #60a5fa; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border-bottom: 1px solid #1f2937; padding: 8px 10px; text-align: left; font-size: 13px; }}
.card {{ background: #0f172a; border: 1px solid #1f2937; border-radius: 10px; padding: 16px; margin: 16px 0; }}
</style>
</head>
<body>
<h1>{html.escape(title)}</h1>
<div class='card'>
{summary}
{chart}
</div>
<div class='card'>
<h2>Top candidates</h2>
<table>
<thead><tr><th>idx</th><th>score</th><th>outputDpi</th><th>syncSpeed</th><th>motivity</th><th>gamma</th><th>smooth</th></tr></thead>
<tbody>
{''.join(table_rows)}
</tbody>
</table>
</div>
</body>
</html>
"""

    out_path.write_text(body, encoding="utf-8")
    return out_path
