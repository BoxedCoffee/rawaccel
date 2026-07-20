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

    fix_segments = []
    cur = []
    for r in rows:
        phase = (r.get("phase") or "").strip()
        tag = (r.get("tag") or "").strip()
        if phase in ("fix_baseline", "fix_tweak") and tag == "combined":
            cur.append(r)
        else:
            if cur:
                fix_segments.append(cur)
                cur = []
    if cur:
        fix_segments.append(cur)

    fix_html = ""
    if fix_segments:
        seg = fix_segments[-1]
        base = []
        tweak = []
        for r in seg:
            phase = (r.get("phase") or "").strip()
            sc = _safe_float(r.get("score"), None)
            if sc is None or not math.isfinite(float(sc)):
                continue
            wp = (r.get("weakness_path") or "").strip()
            item = {"score": float(sc), "weakness_path": wp}
            if phase == "fix_baseline":
                base.append(item)
            else:
                tweak.append(item)

        n = min(len(base), len(tweak))
        if n > 0:
            base = base[:n]
            tweak = tweak[:n]
            b_scores = [x["score"] for x in base]
            t_scores = [x["score"] for x in tweak]
            diffs = [t - b for t, b in zip(t_scores, b_scores)]

            wins = sum(1 for d in diffs if d >= 0.0)
            win_rate = wins / float(len(diffs))

            b_mean = sum(b_scores) / float(len(b_scores))
            t_mean = sum(t_scores) / float(len(t_scores))
            b_std = (sum((x - b_mean) ** 2 for x in b_scores) / float(len(b_scores))) ** 0.5 if len(b_scores) >= 2 else 0.0
            t_std = (sum((x - t_mean) ** 2 for x in t_scores) / float(len(t_scores))) ** 0.5 if len(t_scores) >= 2 else 0.0
            d_mean = t_mean - b_mean
            d_std = (sum((x - d_mean) ** 2 for x in diffs) / float(len(diffs))) ** 0.5 if len(diffs) >= 2 else 0.0
            margin = max(0.5 * d_std, 0.01 * abs(b_mean))

            winner = "Too close"
            if d_mean >= margin and win_rate >= 0.6:
                winner = "Tweak"
            if (-d_mean) >= margin and (1.0 - win_rate) >= 0.6:
                winner = "Baseline"

            def load_wp(wp):
                if not wp:
                    return None
                try:
                    return json.loads((csv_path.parent / wp).read_text(encoding="utf-8"))
                except Exception:
                    return None

            def merge_dir_bins(db_list):
                db_list = [db for db in db_list if isinstance(db, dict) and isinstance(db.get("rows"), list)]
                if not db_list:
                    return None
                bins = int(db_list[0].get("bins", 0) or 0)
                acc = {}
                for db in db_list:
                    for row in db.get("rows", []):
                        if not isinstance(row, dict):
                            continue
                        try:
                            bi = int(row.get("bin"))
                        except Exception:
                            continue
                        n = int(row.get("n", 0) or 0)
                        if n <= 0:
                            continue
                        if bi not in acc:
                            acc[bi] = {
                                "bin": bi,
                                "deg0": float(row.get("deg0", 0.0) or 0.0),
                                "deg1": float(row.get("deg1", 0.0) or 0.0),
                                "n": 0,
                                "miss_num": 0.0,
                                "p90_num": 0.0,
                                "bpar_num": 0.0,
                                "bperp_num": 0.0,
                                "corr_num": 0.0,
                                "move_num": 0.0,
                                "spd_num": 0.0,
                            }
                        a = acc[bi]
                        a["n"] += n
                        a["miss_num"] += float(row.get("miss_rate", 0.0) or 0.0) * n
                        a["p90_num"] += float(row.get("p90_error_px", 0.0) or 0.0) * n
                        a["bpar_num"] += float(row.get("bias_parallel_mean", 0.0) or 0.0) * n
                        a["bperp_num"] += float(row.get("bias_perp_mean", 0.0) or 0.0) * n
                        a["corr_num"] += float(row.get("avg_correction_ms", 0.0) or 0.0) * n
                        a["move_num"] += float(row.get("avg_time_to_move_ms", 0.0) or 0.0) * n
                        a["spd_num"] += float(row.get("speed_mean", 0.0) or 0.0) * n

                rows_out = []
                for bi in sorted(acc.keys()):
                    a = acc[bi]
                    n = max(1, int(a["n"]))
                    rows_out.append(
                        {
                            "bin": int(bi),
                            "deg0": float(a["deg0"]),
                            "deg1": float(a["deg1"]),
                            "n": int(a["n"]),
                            "miss_rate": float(a["miss_num"] / n),
                            "p90_error_px": float(a["p90_num"] / n),
                            "bias_parallel_mean": float(a["bpar_num"] / n),
                            "bias_perp_mean": float(a["bperp_num"] / n),
                            "avg_correction_ms": float(a["corr_num"] / n),
                            "avg_time_to_move_ms": float(a["move_num"] / n),
                            "speed_mean": float(a["spd_num"] / n),
                        }
                    )
                return {"bins": int(bins), "rows": rows_out}

            def collect_side(objs, key):
                out = []
                for o in objs:
                    if not isinstance(o, dict):
                        continue
                    db = o.get("dir_bins")
                    if isinstance(db, dict) and key is None and isinstance(db.get("rows"), list):
                        out.append(db)
                    if isinstance(db, dict) and key is not None:
                        sub = db.get(key)
                        if isinstance(sub, dict) and isinstance(sub.get("rows"), list):
                            out.append(sub)
                return out

            base_w = [load_wp(x.get("weakness_path")) for x in base]
            tweak_w = [load_wp(x.get("weakness_path")) for x in tweak]

            def render_pair(label, base_db, tweak_db):
                if base_db is None and tweak_db is None:
                    return ""
                def wrap(db, title):
                    if db is None:
                        return ""
                    return render_bins({"dir_bins": db}, title)
                left = wrap(base_db, f"{label} baseline")
                right = wrap(tweak_db, f"{label} tweak")
                return "<div style='display:flex;gap:16px;flex-wrap:wrap'>" + left + right + "</div>"

            base_single = merge_dir_bins(collect_side(base_w, None))
            tweak_single = merge_dir_bins(collect_side(tweak_w, None))
            base_micro = merge_dir_bins(collect_side(base_w, "micro"))
            tweak_micro = merge_dir_bins(collect_side(tweak_w, "micro"))
            base_flick = merge_dir_bins(collect_side(base_w, "flick"))
            tweak_flick = merge_dir_bins(collect_side(tweak_w, "flick"))

            tables = ""
            if base_single is not None or tweak_single is not None:
                tables = render_pair("Directional", base_single, tweak_single)
            else:
                tables = render_pair("Micro", base_micro, tweak_micro) + render_pair("Flick", base_flick, tweak_flick)

            fix_html = (
                "<div class='card'>"
                "<h2>Fix weak bins</h2>"
                f"<p><b>Winner</b>: {html.escape(winner)}</p>"
                f"<p>Rounds={n} | Win rate (tweak)={win_rate*100:.0f}% | Mean diff (tweak-baseline)={d_mean:+.4f} (margin {margin:.4f})</p>"
                f"<p>Baseline mean±std: {b_mean:.4f} ± {b_std:.4f} | Tweak mean±std: {t_mean:.4f} ± {t_std:.4f}</p>"
                + tables
                + "</div>"
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
        diag_blocks = ""
        if best_i is not None:
            micro = weakness.get((best_i, "micro"))
            flick = weakness.get((best_i, "flick"))
            single = weakness.get((best_i, "single"))

            def diagnose(obj, label):
                if not isinstance(obj, dict):
                    return ""
                ds = obj.get("dir_summary")
                if not isinstance(ds, dict):
                    return ""
                worst = []
                for k in ("worst_miss", "worst_p90"):
                    xs = ds.get(k)
                    if not isinstance(xs, list):
                        continue
                    for r in xs:
                        if isinstance(r, dict):
                            worst.append(r)
                if not worst:
                    return ""

                uniq = {}
                for r in worst:
                    try:
                        b = int(r.get("bin"))
                    except Exception:
                        continue
                    if b not in uniq:
                        uniq[b] = r

                items = list(uniq.values())
                items.sort(key=lambda r: (float(r.get("miss_rate", 0.0)), float(r.get("p90_error_px", 0.0))), reverse=True)
                items = items[:4]

                sp33 = _safe_float(ds.get("speed_p33"), 0.0) or 0.0
                sp66 = _safe_float(ds.get("speed_p66"), 0.0) or 0.0

                vert_votes = 0
                vert_bias = 0.0
                high_over = 0
                low_under = 0
                for r in items:
                    deg0 = _safe_float(r.get("deg0"), 0.0) or 0.0
                    deg1 = _safe_float(r.get("deg1"), 0.0) or 0.0
                    deg = 0.5 * (deg0 + deg1)
                    rad = math.radians(float(deg))
                    vy = abs(math.sin(rad))
                    bpar = _safe_float(r.get("bias_parallel_mean"), 0.0) or 0.0
                    spd = _safe_float(r.get("speed_mean"), 0.0) or 0.0
                    if vy >= 0.85:
                        vert_votes += 1
                        vert_bias += float(bpar)
                    if sp66 > 0 and spd >= sp66 and bpar >= 2.0:
                        high_over += 1
                    if sp33 > 0 and spd <= sp33 and bpar <= -2.0:
                        low_under += 1

                recs = []
                if vert_votes >= 2:
                    if vert_bias > 2.0:
                        recs.append("Vertical-ish overshoot: decrease yToXRatio")
                    if vert_bias < -2.0:
                        recs.append("Vertical-ish undershoot: increase yToXRatio")
                if high_over >= 2:
                    recs.append("High-speed overshoot: reduce curve aggression (motivity/gamma down or smooth up)")
                if low_under >= 2:
                    recs.append("Low-speed undershoot: increase low-speed gain (motivity/gamma down or syncSpeed up)")

                if not recs:
                    return ""

                lines = "".join(f"<li>{html.escape(s)}</li>" for s in recs)
                return (
                    "<div class='card' style='flex:1'>"
                    f"<h3>Diagnosis ({html.escape(label)})</h3>"
                    f"<ul style='margin:0;padding-left:18px'>{lines}</ul>"
                    "</div>"
                )

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
                    bpar = float(row.get("bias_parallel_mean", 0.0) or 0.0)
                    bperp = float(row.get("bias_perp_mean", 0.0) or 0.0)
                    corr = float(row.get("avg_correction_ms", 0.0) or 0.0)
                    spd = float(row.get("speed_mean", 0.0) or 0.0)
                    alpha = max(0.0, min(0.75, miss))
                    bar = f"<div style='height:10px;width:{max(0.0,min(1.0,miss))*100:.0f}%;background:rgba(239,68,68,{alpha:.3f});border-radius:5px'></div>"
                    trows.append(
                        "<tr>"
                        + td(f"{deg0:.0f}–{deg1:.0f}°")
                        + td(n, align="right")
                        + td(f"{miss:.3f}", align="right")
                        + td(f"{p90:.1f}", align="right")
                        + td(f"{bpar:+.1f}", align="right")
                        + td(f"{bperp:+.1f}", align="right")
                        + td(f"{corr:.0f}", align="right")
                        + td(f"{spd:.0f}", align="right")
                        + f"<td style='width:160px'>{bar}</td>"
                        + "</tr>"
                    )

                return (
                    "<div class='card' style='flex:1'>"
                    f"<h3>{html.escape(label)} ({bins} bins)</h3>"
                    "<table>"
                    "<thead><tr><th>dir</th><th style='text-align:right'>n</th><th style='text-align:right'>miss</th><th style='text-align:right'>p90(px)</th><th style='text-align:right'>b‖</th><th style='text-align:right'>b⊥</th><th style='text-align:right'>corr(ms)</th><th style='text-align:right'>spd</th><th></th></tr></thead>"
                    f"<tbody>{''.join(trows)}</tbody>"
                    "</table>"
                    "</div>"
                )

            if isinstance(single, dict):
                drill_blocks = render_bins(single, "Directional weakness")
                diag_blocks = diagnose(single, "single")
            else:
                blocks = []
                diags = []
                if isinstance(micro, dict):
                    blocks.append(render_bins(micro, "Micro"))
                    d = diagnose(micro, "micro")
                    if d:
                        diags.append(d)
                if isinstance(flick, dict):
                    blocks.append(render_bins(flick, "Flick"))
                    d = diagnose(flick, "flick")
                    if d:
                        diags.append(d)
                if blocks:
                    drill_blocks = "<div style='display:flex;gap:16px;flex-wrap:wrap'>" + "".join(blocks) + "</div>"
                if diags:
                    diag_blocks = "<div style='display:flex;gap:16px;flex-wrap:wrap'>" + "".join(diags) + "</div>"

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
            + diag_blocks
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
  {fix_html}
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
