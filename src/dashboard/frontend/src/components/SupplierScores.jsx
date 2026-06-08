function formatCurrency(n) {
  return "$" + Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 })
}

const RANK_BADGES = {
  1: { label: "1st", bg: "#f59e0b", color: "#fff" },
  2: { label: "2nd", bg: "#6b7280", color: "#fff" },
  3: { label: "3rd", bg: "#92400e", color: "#fff" },
}

function ReliabilityBar({ score }) {
  const color = score >= 8 ? "#22c55e" : score >= 5 ? "#eab308" : "#ef4444"
  return (
    <div style={{ marginTop: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
        <span style={{ fontSize: 11, color: "var(--text-muted)" }}>Reliability Score</span>
        <span style={{ fontSize: 11, fontWeight: 700, color: "var(--text-secondary)" }}>
          {score != null ? score.toFixed(1) : "—"}/10
        </span>
      </div>
      <div style={{ height: 4, background: "var(--border)", borderRadius: 999 }}>
        <div style={{
          height: 4, width: `${Math.min((score / 10) * 100, 100)}%`,
          background: color, borderRadius: 999, transition: "width 0.4s"
        }} />
      </div>
    </div>
  )
}

function MetricCell({ label, value }) {
  return (
    <div>
      <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 2 }}>{label}</div>
      <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)" }}>{value}</div>
    </div>
  )
}

export default function SupplierScores({ result }) {
  const alternatives = result?.raw?.suggested_alternatives || []

  if (alternatives.length === 0) {
    return (
      <div style={{
        background: "var(--bg-card)", border: "1px solid var(--border)",
        borderRadius: 16, padding: 24, marginBottom: 24,
        display: "flex", flexDirection: "column", alignItems: "center",
        justifyContent: "center", minHeight: 120, color: "var(--text-muted)",
        fontSize: 14
      }}>
        Run a simulation to see AI-ranked supplier alternatives.
      </div>
    )
  }

  return (
    <div style={{
      background: "var(--bg-card)", border: "1px solid var(--border)",
      borderRadius: 16, padding: 24, marginBottom: 24
    }}>
      <div style={{ marginBottom: 20 }}>
        <div style={{ fontSize: 16, fontWeight: 700, color: "var(--text-primary)" }}>
          Alternative Suppliers
        </div>
        <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>
          AI-ranked by reliability, price &amp; lead time
        </div>
      </div>

      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
        gap: 16
      }}>
        {alternatives.map((s) => {
          const badge = RANK_BADGES[s.rank] || RANK_BADGES[3]
          const premium = s.total_cost_premium_usd ?? 0

          return (
            <div key={s.supplier_id || s.rank} style={{
              background: "var(--bg-card-hover)", border: "1px solid var(--border)",
              borderRadius: 14, padding: 20, position: "relative"
            }}>
              {/* Rank badge */}
              <div style={{
                position: "absolute", top: 14, right: 14,
                background: badge.bg, color: badge.color,
                fontSize: 11, fontWeight: 700,
                padding: "3px 8px", borderRadius: 999
              }}>
                {badge.label}
              </div>

              {/* Name + country */}
              <div style={{ paddingRight: 40 }}>
                <div style={{ fontSize: 15, fontWeight: 700, color: "var(--text-primary)" }}>
                  {s.name}
                </div>
                <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>
                  {s.country}
                </div>
              </div>

              {/* Metrics grid */}
              <div style={{
                display: "grid", gridTemplateColumns: "1fr 1fr",
                gap: 12, marginTop: 16
              }}>
                <MetricCell label="Lead Time" value={`${s.lead_time_days} days`} />
                <MetricCell label="Unit Price" value={s.unit_price_usd != null ? `$${s.unit_price_usd.toFixed(2)}/unit` : "—"} />
                <MetricCell
                  label="On-Time Rate"
                  value={s.on_time_rate != null ? `${(s.on_time_rate * 100).toFixed(0)}%` : "No history"}
                />
                <MetricCell
                  label="Reviews"
                  value={s.avg_review_rating != null ? `${s.avg_review_rating.toFixed(1)}/5` : "No reviews"}
                />
              </div>

              <ReliabilityBar score={s.dynamic_reliability_score} />

              {/* Cost vs primary */}
              <div style={{ marginTop: 10, fontSize: 13 }}>
                {premium > 0 && (
                  <span style={{ color: "#ef4444", fontWeight: 600 }}>
                    +{formatCurrency(premium)} vs primary
                  </span>
                )}
                {premium < 0 && (
                  <span style={{ color: "#22c55e", fontWeight: 600 }}>
                    {formatCurrency(premium)} savings vs primary
                  </span>
                )}
                {premium === 0 && (
                  <span style={{ color: "var(--text-muted)" }}>Same price as primary</span>
                )}
              </div>

              {/* Tradeoff summary */}
              {s.tradeoff_summary && (
                <div style={{
                  marginTop: 10, fontSize: 12,
                  color: "var(--text-muted)", fontStyle: "italic",
                  lineHeight: 1.5
                }}>
                  {s.tradeoff_summary}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
