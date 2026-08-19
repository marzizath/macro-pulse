export default function HeroSplit({ summary, period, onPeriodChange }) {
  if (!summary) return null;

  const { raw_total, true_total, saved, match_rate } = summary;
  const pct = raw_total > 0 ? Math.min(100, Math.round((true_total / raw_total) * 100)) : 0;

  return (
    <div className="card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h2>True spend this {period}</h2>
        <div className="period-toggle">
          <button
            className={period === "week" ? "active" : ""}
            onClick={() => onPeriodChange("week")}
          >
            Week
          </button>
          <button
            className={period === "month" ? "active" : ""}
            onClick={() => onPeriodChange("month")}
          >
            Month
          </button>
        </div>
      </div>

      <div className="hero-numbers">
        <span className="hero-true mono">${true_total.toFixed(2)}</span>
        <span className="hero-raw mono">bank saw ${raw_total.toFixed(2)}</span>
      </div>

      <div className="hero-bar">
        <div className="hero-bar-fill" style={{ width: `${pct}%` }} />
      </div>

      <div className="stat-grid">
        <div className="stat-box">
          <div className="label">Saved via splits</div>
          <div className="value mono amount-pos">${saved.toFixed(2)}</div>
        </div>
        <div className="stat-box">
          <div className="label">Match rate</div>
          <div className="value mono">{Math.round(match_rate * 100)}%</div>
        </div>
      </div>
    </div>
  );
}
