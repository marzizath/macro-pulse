"""
Builds a static dashboard (docs/index.html) from the historical archive.
Deployed via GitHub Pages serving the /docs folder - no server, no hosting
cost, updates automatically each time the daily workflow commits new
history and this script re-runs.

Uses Chart.js from a CDN for the line charts - the data itself is embedded
directly in the HTML so the page works standalone (no fetch/CORS issues).
"""
import json
from datetime import datetime
from history_store import load_all_runs

OUTPUT_PATH = "docs/index.html"


def _build_series(runs: list) -> dict:
    """asset name -> {dates: [...], pct_changes: [...]}"""
    series = {}
    for run in runs:
        for a in run.get("assets", []):
            if "error" in a:
                continue
            name = a["name"]
            series.setdefault(name, {"dates": [], "pct_changes": [], "anomaly": []})
            series[name]["dates"].append(run["date"])
            series[name]["pct_changes"].append(a["pct_change"])
            series[name]["anomaly"].append(a.get("anomaly", False))
    return series


def _flagged_history_rows(runs: list) -> str:
    rows = ""
    for run in reversed(runs):
        if not run.get("flagged"):
            continue
        rows += (
            f'<tr><td>{run["date"]}</td>'
            f'<td>{", ".join(run["flagged"])}</td></tr>'
        )
    return rows or '<tr><td colspan="2">No anomalies flagged yet.</td></tr>'


def build_dashboard():
    runs = load_all_runs()
    series = _build_series(runs)
    colors = ["#f0b429", "#0f9d58", "#d93025", "#4285f4", "#a142f4",
              "#00acc1", "#ff6f00", "#795548", "#607d8b"]

    datasets_js = []
    for i, (name, s) in enumerate(series.items()):
        color = colors[i % len(colors)]
        datasets_js.append({
            "label": name,
            "data": s["pct_changes"],
            "borderColor": color,
            "backgroundColor": color + "20",
            "tension": 0.25,
            "pointRadius": [4 if a else 1.5 for a in s["anomaly"]],
        })
    all_dates = series[next(iter(series))]["dates"] if series else []

    html = f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Macro Pulse Dashboard</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
  body {{ font-family: -apple-system, 'Segoe UI', Roboto, Arial, sans-serif;
          background:#f4f5f7; color:#1a1d26; margin:0; padding:20px; }}
  .wrap {{ max-width: 900px; margin: 0 auto; }}
  h1 {{ font-size: 22px; }}
  .meta {{ color:#6b7280; font-size:13px; margin-bottom:20px; }}
  .card {{ background:#fff; border-radius:10px; padding:18px; margin-bottom:18px;
           box-shadow: 0 1px 3px rgba(0,0,0,0.06); }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  th, td {{ text-align:left; padding:8px 10px; border-bottom:1px solid #eceef1; }}
  th {{ color:#6b7280; text-transform:uppercase; font-size:11px; }}
  .disclaimer {{ color:#9aa0aa; font-size:11px; text-align:center; margin-top:20px; }}
</style>
</head><body>
<div class="wrap">
  <h1>&#9889; Macro Pulse Dashboard</h1>
  <div class="meta">{len(runs)} days recorded &bull; last updated {datetime.now().strftime('%d %b %Y')}</div>

  <div class="card">
    <h3>Daily % change by asset</h3>
    <canvas id="mainChart" height="110"></canvas>
  </div>

  <div class="card">
    <h3>Flagged anomaly history</h3>
    <table>
      <tr><th>Date</th><th>Assets flagged</th></tr>
      {_flagged_history_rows(runs)}
    </table>
  </div>

  <p class="disclaimer">Informational context only &mdash; not investment advice, not a trading signal.</p>
</div>

<script>
const ctx = document.getElementById('mainChart');
new Chart(ctx, {{
  type: 'line',
  data: {{
    labels: {json.dumps(all_dates)},
    datasets: {json.dumps(datasets_js)}
  }},
  options: {{
    responsive: true,
    interaction: {{ mode: 'index', intersect: false }},
    plugins: {{ legend: {{ position: 'bottom', labels: {{ boxWidth: 12, font: {{ size: 11 }} }} }} }},
    scales: {{ y: {{ ticks: {{ callback: (v) => v + '%' }} }} }}
  }}
}});
</script>
</body></html>"""

    import os
    os.makedirs("docs", exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    return OUTPUT_PATH


if __name__ == "__main__":
    path = build_dashboard()
    print(f"Dashboard written to {path}")
