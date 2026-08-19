export default function Receivables({ receivables, onSettle }) {
  return (
    <div className="card">
      <h2>Who owes you</h2>
      {receivables.length === 0 && <div className="empty-state">Nobody owes you right now.</div>}
      {receivables.map((r) => (
        <div className="row" key={r.id}>
          <div>
            <div className="row-title">{r.debtor_name}</div>
            <div className="row-sub">
              {r.days_open} day{r.days_open === 1 ? "" : "s"} open
              {r.days_open > 14 && <span style={{ color: "var(--amber)" }}> &middot; overdue</span>}
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span className="mono">${r.amount.toFixed(2)}</span>
            <button className="btn btn-ghost" onClick={() => onSettle(r.id)}>
              Mark settled
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
