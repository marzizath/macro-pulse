import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import HeroSplit from "./components/HeroSplit.jsx";
import Receivables from "./components/Receivables.jsx";
import ReviewQueue from "./components/ReviewQueue.jsx";
import TransactionList from "./components/TransactionList.jsx";

export default function App() {
  const [period, setPeriod] = useState("week");
  const [summary, setSummary] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [receivables, setReceivables] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async (activePeriod) => {
    try {
      setError(null);
      const [summaryRes, txnRes, recvRes] = await Promise.all([
        api.getSummary(activePeriod),
        api.getTransactions({ limit: 100 }),
        api.getReceivables(true),
      ]);
      setSummary(summaryRes);
      setTransactions(txnRes);
      setReceivables(recvRes);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(period);
  }, [period, load]);

  const handleConfirm = async (id) => {
    await api.patchTransaction(id, { action: "confirm" });
    load(period);
  };

  const handleReject = async (id) => {
    await api.patchTransaction(id, { action: "reject" });
    load(period);
  };

  const handleSettle = async (id) => {
    await api.settleReceivable(id);
    load(period);
  };

  const flagged = transactions.filter((t) => t.match_status === "flagged");

  return (
    <div className="app-shell">
      <header className="app-header">
        <h1>Net Reconciler</h1>
        <span className="pill">true spend</span>
      </header>

      {loading && <div className="loading">Loading…</div>}
      {error && <div className="error">{error}</div>}

      {!loading && !error && (
        <>
          <HeroSplit summary={summary} period={period} onPeriodChange={setPeriod} />
          <ReviewQueue flagged={flagged} onConfirm={handleConfirm} onReject={handleReject} />
          <Receivables receivables={receivables} onSettle={handleSettle} />
          <TransactionList transactions={transactions} />
        </>
      )}
    </div>
  );
}
