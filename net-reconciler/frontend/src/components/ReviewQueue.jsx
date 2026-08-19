export default function ReviewQueue({ flagged, onConfirm, onReject }) {
  if (flagged.length === 0) return null;

  return (
    <div className="card">
      <h2>Review queue ({flagged.length})</h2>
      {flagged.map((t) => (
        <div className="review-item" key={t.id}>
          <div className="row-title">{t.description}</div>
          <div className="review-compare">
            <div className="review-side">
              <div className="label">Bank</div>
              <div className="val mono">${t.amount.toFixed(2)}</div>
              <div className="row-sub">{t.post_date}</div>
            </div>
            <div className="review-side">
              <div className="label">Splitwise candidate</div>
              {t.candidate_description ? (
                <>
                  <div className="val mono">${t.candidate_amount?.toFixed(2)}</div>
                  <div className="row-sub">{t.candidate_description}</div>
                </>
              ) : (
                <div className="row-sub">No single candidate - amount matched two+ expenses equally</div>
              )}
            </div>
          </div>
          <div className="review-actions">
            <button className="btn btn-accent" onClick={() => onConfirm(t.id)}>Confirm</button>
            <button className="btn btn-ghost" onClick={() => onReject(t.id)}>Reject</button>
          </div>
        </div>
      ))}
    </div>
  );
}
