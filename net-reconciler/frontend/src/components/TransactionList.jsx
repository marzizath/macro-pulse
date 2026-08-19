import { useState } from "react";

const FILTERS = [
  { key: "all", label: "All" },
  { key: "matched", label: "Matched" },
  { key: "personal", label: "Personal" },
  { key: "pending_settle", label: "Pending" },
  { key: "flagged", label: "Flagged" },
];

export default function TransactionList({ transactions }) {
  const [filter, setFilter] = useState("all");
  const visible = filter === "all" ? transactions : transactions.filter((t) => t.match_status === filter);

  return (
    <div className="card">
      <h2>Transactions</h2>
      <div className="filter-pills">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            className={filter === f.key ? "active" : ""}
            onClick={() => setFilter(f.key)}
          >
            {f.label}
          </button>
        ))}
      </div>

      {visible.length === 0 && <div className="empty-state">No transactions here.</div>}
      {visible.map((t) => (
        <div className="row" key={t.id}>
          <div>
            <div className="row-title">{t.description}</div>
            <div className="row-sub">
              {t.post_date} &middot; <StatusPill status={t.match_status} />
            </div>
          </div>
          <span className={`mono ${t.direction === "credit" ? "amount-pos" : "amount-neg"}`}>
            {t.direction === "credit" ? "+" : "-"}${t.amount.toFixed(2)}
          </span>
        </div>
      ))}
    </div>
  );
}

function StatusPill({ status }) {
  return <span>{status.replace("_", " ")}</span>;
}
