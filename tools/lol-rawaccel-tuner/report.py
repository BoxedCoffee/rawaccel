import csv
import html
import json
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

    weakness = {}
    for r in rows:
        idx = r.get("idx")
        if idx is None:
            idx = r.get("iter")
        tag = (r.get("tag") or "").strip()
        wp = (r.get("weakness_path") or "").strip()
        if not idx or not tag or not wp:
            continue
        try:
            i = int(float(idx))
        except Exception:
            continue
        try:
            obj = json.loads((csv_path.parent / wp).read_text(encoding="utf-8"))
        except Exception:
            continue
        weakness[(i, tag)] = obj

    combined = []
    for r in rows:
        tag = (r.get("tag") or "").strip()
        if tag in ("single", "combined"):
            score = _safe_float(r.get("score"), None)
            metric_score = _safe_float(r.get("metric_score"), None)
            idx = _safe_float(r.get("idx"), None)
            if idx is None:
                idx = _safe_float(r.get("iter"), None)
            if score is None or idx is None or not math.isfinite(score):
                continue
            combined.append((int(idx), float(metric_score) if metric_score is not None else float(score), float(score), r))

    combined.sort(key=lambda x: x[0])

    confirm_segments = []
    cur = []
    for r in rows:
        phase = (r.get("phase") or "").strip()
        tag = (r.get("tag") or "").strip()
        if phase == "confirm" and tag in ("best", "second", "challenger"):
            cur.append(r)
        else:
            if cur:
                confirm_segments.append(cur)
                cur = []
    if cur:
        confirm_segments.append(cur)

    confirm_html = ""
    if confirm_segments:
        seg = confirm_segments[-1]
        pairs = []
        buf = {}
        for r in seg:
            tag = (r.get("tag") or "").strip()
            sc = _safe_float(r.get("score"), None)
            if sc is None or not math.isfinite(float(sc)):
                continue
            if tag == "challenger":
                tag = "second"
            if tag not in ("best", "second"):
                continue
            buf[tag] = float(sc)
            if "best" in buf and "second" in buf:
                pairs.append({"best": float(buf["best"]), "second": float(buf["second"])})
                buf = {}

        if pairs:
            best_scores = [p["best"] for p in pairs]
            second_scores = [p["second"] for p in pairs]
            diffs = [b - s for b, s in zip(best_scores, second_scores)]

            wins = sum(1 for d in diffs if d >= 0.0)
            win_rate = wins / float(len(diffs)) if diffs else 0.0

            best_mean = sum(best_scores) / float(len(best_scores))
            second_mean = sum(second_scores) / float(len(second_scores))
            best_std = (sum((x - best_mean) ** 2 for x in best_scores) / float(len(best_scores))) ** 0.5 if len(best_scores) >= 2 else 0.0
            second_std = (sum((x - second_mean) ** 2 for x in second_scores) / float(len(second_scores))) ** 0.5 if len(second_scores) >= 2 else 0.0
            diff_mean = best_mean - second_mean
            diff_std = (sum((x - diff_mean) ** 2 for x in diffs) / float(len(diffs))) ** 0.5 if len(diffs) >= 2 else 0.0
            margin = max(0.5 * diff_std, 0.01 * abs(second_mean))

            winner = "Too close"
            if diff_mean >= margin and win_rate >= 0.6:
                winner = "Best"
            if (-diff_mean) >= margin and (1.0 - win_rate) >= 0.6:
                winner = "#2"

            confirm_html = (
                "<div class='card'>"
                "<h2>Confirm</h2>"
                f"<p><b>Winner</b>: {html.escape(winner)}</p>"
                f"<p>Rounds={len(pairs)} | Win rate (Best)={win_rate*100:.0f}% | Mean diff (Best-#2)={diff_mean:+.4f} (margin {margin:.4f})</p>"
                f"<p>Best mean±std: {best_mean:.4f} ± {best_std:.4f} | #2 mean±std: {second_mean:.4f} ± {second_std:.4f}</p>"
                "</div>"
            )

    best = max(combined, key=lambda x: x[1])[3] if combined else None
    top = sorted(combined, key=lambda x: x[1], reverse=True)[:10]

    chart = _svg_line([(i, metric_s) for i, metric_s, _, _ in combined], 900, 260)

    def td(s):
        return f"<td>{html.escape(str(s))}</td>"

    table_rows = []
    for _, metric_s, raw_s, r in top:
        score_mean = _safe_float(r.get("score_mean"), None)
        score_std = _safe_float(r.get("score_std"), None)
        table_rows.append(
            "<tr>"
            + td(r.get("idx") or r.get("iter"))
            + td(f"{metric_s:.4f}")
            + td(f"{raw_s:.4f}")
            + td(f"{score_mean:.4f}" if score_mean is not None else "")
            + td(f"{score_std:.4f}" if score_std is not None else "")
            + td(r.get("outputDpi"))
            + td(r.get("syncSpeed"))
            + td(r.get("motivity"))
            + td(r.get("gamma"))
            + td(r.get("smooth"))
            + td(r.get("yToXRatio"))
            + "</tr>"
        )

    summary = ""
    if best is not None:
        best_idx = best.get("idx")
        if best_idx is None:
            best_idx = best.get("iter")
        try:
            best_i = int(float(best_idx)) if best_idx is not None else None
        except Exception:
            best_i = None

        drill_blocks = ""
        if best_i is not None:
            micro = weakness.get((best_i, "micro"))
            flick = weakness.get((best_i, "flick"))
            single = weakness.get((best_i, "single"))

            def render_bins(obj, label):
                if not isinstance(obj, dict):
                    return ""
                db = obj.get("dir_bins")
                if not isinstance(db, dict):
                    return ""
                bins = int(db.get("bins", 0) or 0)
                rr = db.get("rows")
                if not isinstance(rr, list) or not rr:
                    return ""

                def td(s, align=None):
                    if align:
                        return f"<td style='text-align:{align}'>{html.escape(str(s))}</td>"
                    return f"<td>{html.escape(str(s))}</td>"

                trows = []
                for row in rr:
                    if not isinstance(row, dict):
                        continue
                    deg0 = float(row.get("deg0", 0.0))
                    deg1 = float(row.get("deg1", 0.0))
                    n = int(row.get("n", 0) or 0)
                    miss = float(row.get("miss_rate", 0.0) or 0.0)
                    p90 = float(row.get("p90_error_px", 0.0) or 0.0)
                    corr = float(row.get("avg_correction_ms", 0.0) or 0.0)
                    alpha = max(0.0, min(0.75, miss))
                    bar = f"<div style='height:10px;width:{max(0.0,min(1.0,miss))*100:.0f}%;background:rgba(239,68,68,{alpha:.3f});border-radius:5px'></div>"
                    trows.append(
                        "<tr>"
                        + td(f"{deg0:.0f}–{deg1:.0f}°")
                        + td(n, align="right")
                        + td(f"{miss:.3f}", align="right")
                        + td(f"{p90:.1f}", align="right")
                        + td(f"{corr:.0f}", align="right")
                        + f"<td style='width:160px'>{bar}</td>"
                        + "</tr>"
                    )

                return (
                    "<div class='card' style='flex:1'>"
                    f"<h3>{html.escape(label)} ({bins} bins)</h3>"
                    "<table>"
                    "<thead><tr><th>dir</th><th style='text-align:right'>n</th><th style='text-align:right'>miss</th><th style='text-align:right'>p90(px)</th><th style='text-align:right'>corr(ms)</th><th></th></tr></thead>"
                    f"<tbody>{''.join(trows)}</tbody>"
                    "</table>"
                    "</div>"
                )

            if isinstance(single, dict):
                drill_blocks = render_bins(single, "Directional weakness")
            else:
                blocks = []
                if isinstance(micro, dict):
                    blocks.append(render_bins(micro, "Micro"))
                if isinstance(flick, dict):
                    blocks.append(render_bins(flick, "Flick"))
                if blocks:
                    drill_blocks = "<div style='display:flex;gap:16px;flex-wrap:wrap'>" + "".join(blocks) + "</div>"

        raw_s = _safe_float(best.get("score"), None)
        metric_s = _safe_float(best.get("metric_score"), None)
        score_mean = _safe_float(best.get("score_mean"), None)
        score_std = _safe_float(best.get("score_std"), None)
        sel = (best.get("selection_metric") or "").strip()
        k = _safe_float(best.get("stability_k"), None)

        score_bits = []
        if metric_s is not None:
            score_bits.append(f"metric={metric_s:.4f}")
        if raw_s is not None:
            score_bits.append(f"raw={raw_s:.4f}")
        if score_mean is not None and score_std is not None:
            score_bits.append(f"mean±std={score_mean:.4f}±{score_std:.4f}")
        if sel:
            if k is not None:
                score_bits.append(f"sel={sel} (k={k:.2f})")
            else:
                score_bits.append(f"sel={sel}")

        summary = (
            f"<p><b>Best</b> {html.escape(' | '.join(score_bits))} "
            f"DPI={html.escape(best.get('outputDpi',''))} syncSpeed={html.escape(best.get('syncSpeed',''))} "
            f"motivity={html.escape(best.get('motivity',''))} gamma={html.escape(best.get('gamma',''))} smooth={html.escape(best.get('smooth',''))} yToXRatio={html.escape(best.get('yToXRatio',''))}</p>"
            + drill_blocks
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
h3 {{ margin: 0 0 10px 0; font-size: 15px; color: #e5e7eb; }}
</style>
</head>
<body>
<h1>{html.escape(title)}</h1>
  <div class='card'>
  {summary}
  {chart}
  </div>
  {confirm_html}
  <div class='card'>
  <h2>Top candidates</h2>
<table>
 <thead><tr><th>idx</th><th>metric</th><th>raw</th><th>mean</th><th>std</th><th>outputDpi</th><th>syncSpeed</th><th>motivity</th><th>gamma</th><th>smooth</th><th>yToXRatio</th></tr></thead>
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
