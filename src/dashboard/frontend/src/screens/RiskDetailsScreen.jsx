import { useState, useEffect } from "react"

const API = "http://localhost:8000"

function formatExposure(usd) {
  if (!usd) return "$0"
  if (usd >= 1_000_000) return `$${(usd / 1_000_000).toFixed(1)}M`
  if (usd >= 1_000) return `$${Math.round(usd / 1_000)}K`
  return `$${Number(usd).toLocaleString("en-US")}`
}

function ConfidenceBar({ value, label }) {
  const pct = Math.round(Math.min(100, Math.max(0, value * 100)))
  const color = pct >= 80 ? "#22c55e" : pct >= 60 ? "#f97316" : "#ef4444"
  return (
    <div>
      {label && (
        <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 4 }}>{label}</div>
      )}
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <div style={{ flex: 1, height: 6, borderRadius: 4, background: "var(--border)", overflow: "hidden" }}>
          <div style={{ width: `${pct}%`, height: "100%", background: color, borderRadius: 4, transition: "width 0.4s ease" }} />
        </div>
        <span style={{ fontSize: 12, fontWeight: 700, color, minWidth: 36 }}>{pct}%</span>
      </div>
    </div>
  )
}

function ScoreBar({ value, max = 1, label }) {
  const pct = Math.round(Math.min(100, (value / max) * 100))
  const color = pct >= 70 ? "#22c55e" : pct >= 40 ? "#f97316" : "#ef4444"
  return (
    <div>
      {label && <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 3 }}>{label}</div>}
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <div style={{ flex: 1, height: 5, borderRadius: 3, background: "var(--border)", overflow: "hidden" }}>
          <div style={{ width: `${pct}%`, height: "100%", background: color, borderRadius: 3 }} />
        </div>
        <span style={{ fontSize: 11, color, fontWeight: 600, minWidth: 30 }}>{pct}%</span>
      </div>
    </div>
  )
}

export default function RiskDetailsScreen({ businessId, onSimulate, refreshKey }) {
  const [analysis, setAnalysis] = useState(null)
  const [loading, setLoading]   = useState(true)

  useEffect(() => {
    async function fetchAnalysis() {
      setLoading(true)
      try {
        const res = await fetch(`${API}/api/latest-analysis?business_id=${businessId}`)
        if (res.ok) setAnalysis(await res.json())
      } finally {
        setLoading(false)
      }
    }
    fetchAnalysis()
  }, [businessId, refreshKey])

  if (loading) {
    return (
      <div style={{ padding: 60, textAlign: "center", color: "var(--text-muted)", fontSize: 14 }}>
        Loading analysis…
      </div>
    )
  }

  if (!analysis?.has_result) {
    return (
      <div style={{ maxWidth: 600, margin: "80px auto", textAlign: "center", padding: "0 32px" }}>
        <div style={{ fontSize: 48, marginBottom: 16 }}>🔍</div>
        <div style={{ fontSize: 18, fontWeight: 700, color: "var(--text-primary)", marginBottom: 8 }}>
          No Analysis Yet
        </div>
        <div style={{ fontSize: 14, color: "var(--text-secondary)", marginBottom: 24 }}>
          Run a simulation to see the agent's risk analysis, affected suppliers, and recommendations.
        </div>
        <button
          onClick={onSimulate}
          style={{
            background: "rgba(96,165,250,0.15)", border: "1px solid rgba(96,165,250,0.4)",
            borderRadius: 10, color: "#60a5fa", fontSize: 14, fontWeight: 600,
            padding: "10px 24px", cursor: "pointer",
          }}
        >
          Run Analysis
        </button>
      </div>
    )
  }

  const {
    severity_score, calibration_confidence, exposure_usd,
    headline, disruption_type, disruption_region,
    signals_detected, affected_suppliers, suggested_alternatives,
    black_swan_detected,
  } = analysis

  const severityNum = Number(severity_score || 0)
  const severityColor = severityNum >= 8 ? "#ef4444" : severityNum >= 5 ? "#f97316" : "#eab308"
  const severityLabel = severityNum >= 8 ? "HIGH RISK" : severityNum >= 5 ? "ELEVATED" : "MODERATE"

  return (
    <div style={{ maxWidth: 960, margin: "0 auto", padding: "32px 32px" }}>

      {/* Header */}
      <div style={{ marginBottom: 28 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>
          Active Risk Analysis
        </h1>
        {black_swan_detected && (
          <div style={{
            marginTop: 10, background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.4)",
            borderRadius: 8, padding: "8px 14px", display: "inline-flex", alignItems: "center", gap: 8,
          }}>
            <span style={{ fontSize: 16 }}>🦢</span>
            <span style={{ fontSize: 13, fontWeight: 600, color: "#ef4444" }}>
              Black Swan Event Detected — Requires Human Review
            </span>
          </div>
        )}
      </div>

      {/* Disruption summary */}
      <div style={{
        background: "var(--bg-card)", border: `1px solid var(--border)`,
        borderLeft: `4px solid ${severityColor}`,
        borderRadius: 12, padding: "20px 24px", marginBottom: 24,
        boxShadow: severityNum >= 8 ? `0 0 14px rgba(239,68,68,0.15)` : "none",
      }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 12 }}>
          <div style={{ flex: 1 }}>
            <div style={{
              fontSize: 11, fontWeight: 700, color: severityColor,
              textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 6,
            }}>
              {severityLabel}
            </div>
            {headline && (
              <div style={{ fontSize: 16, fontWeight: 600, color: "var(--text-primary)", marginBottom: 8, lineHeight: 1.5 }}>
                {headline}
              </div>
            )}
            <div style={{ display: "flex", gap: 20, flexWrap: "wrap" }}>
              {disruption_type && (
                <span style={{ fontSize: 13, color: "var(--text-secondary)" }}>
                  <span style={{ color: "var(--text-muted)" }}>Type: </span>{disruption_type}
                </span>
              )}
              {disruption_region && (
                <span style={{ fontSize: 13, color: "var(--text-secondary)" }}>
                  <span style={{ color: "var(--text-muted)" }}>Region: </span>{disruption_region}
                </span>
              )}
              {exposure_usd > 0 && (
                <span style={{ fontSize: 13, color: "#f97316", fontWeight: 600 }}>
                  Exposure: {formatExposure(exposure_usd)}
                </span>
              )}
            </div>
          </div>
          <div style={{ textAlign: "right", minWidth: 100 }}>
            <div style={{ fontSize: 42, fontWeight: 800, color: severityColor, lineHeight: 1 }}>
              {Math.round(severityNum * 10)}
            </div>
            <div style={{ fontSize: 12, color: "var(--text-muted)" }}>/ 100</div>
            <div style={{ marginTop: 10 }}>
              <ConfidenceBar value={calibration_confidence} label="Confidence" />
            </div>
          </div>
        </div>
      </div>

      {/* Agent Reasoning */}
      {(signals_detected || []).length > 0 && (
        <div style={{
          background: "rgba(59,130,246,0.05)", border: "1px solid rgba(59,130,246,0.2)",
          borderRadius: 12, padding: "18px 22px", marginBottom: 24,
        }}>
          <div style={{
            fontSize: 11, fontWeight: 600, color: "#60a5fa",
            textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 12,
          }}>
            Why Did the Agent Flag This?
          </div>
          <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
            {signals_detected.map((signal, i) => (
              <li key={i} style={{
                fontSize: 14, color: "var(--text-primary)", lineHeight: 1.6,
                paddingLeft: 20, position: "relative", marginBottom: 4,
              }}>
                <span style={{ position: "absolute", left: 0, color: "#60a5fa" }}>•</span>
                {signal}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Affected Suppliers */}
      {(affected_suppliers || []).length > 0 && (
        <div style={{ marginBottom: 24 }}>
          <h2 style={{ fontSize: 15, fontWeight: 700, color: "var(--text-primary)", marginBottom: 12 }}>
            Affected Suppliers
          </h2>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 12 }}>
            {affected_suppliers.map((s, i) => (
              <div key={i} style={{
                background: "var(--bg-card)", border: "1px solid var(--border)",
                borderLeft: "3px solid #ef4444", borderRadius: 10, padding: "14px 16px",
              }}>
                <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)", marginBottom: 4 }}>
                  {s.name || s.supplier_name || s.supplier_id}
                </div>
                {s.country && (
                  <div style={{ fontSize: 12, color: "var(--text-muted)" }}>{s.country}</div>
                )}
                {s.exposure_usd > 0 && (
                  <div style={{ fontSize: 12, color: "#f97316", fontWeight: 600, marginTop: 4 }}>
                    Exposure: {formatExposure(s.exposure_usd)}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recommended Alternatives */}
      {(suggested_alternatives || []).length > 0 && (
        <div>
          <h2 style={{ fontSize: 15, fontWeight: 700, color: "var(--text-primary)", marginBottom: 12 }}>
            Recommended Alternatives
          </h2>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {suggested_alternatives.map((alt, i) => (
              <div key={i} style={{
                background: "var(--bg-card)", border: "1px solid var(--border)",
                borderLeft: `3px solid ${i === 0 ? "#22c55e" : i === 1 ? "#60a5fa" : "var(--border)"}`,
                borderRadius: 12, padding: "18px 20px",
              }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 12 }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
                      <span style={{
                        background: i === 0 ? "rgba(34,197,94,0.15)" : "rgba(96,165,250,0.12)",
                        color: i === 0 ? "#22c55e" : "#60a5fa",
                        fontSize: 11, fontWeight: 700, padding: "2px 8px",
                        borderRadius: 20, border: `1px solid ${i === 0 ? "rgba(34,197,94,0.3)" : "rgba(96,165,250,0.3)"}`,
                      }}>
                        #{alt.rank}
                      </span>
                      <span style={{ fontSize: 15, fontWeight: 700, color: "var(--text-primary)" }}>
                        {alt.name}
                      </span>
                      <span style={{ fontSize: 13, color: "var(--text-muted)" }}>{alt.country}</span>
                    </div>

                    {alt.tradeoff_summary && (
                      <div style={{ fontSize: 13, color: "var(--text-secondary)", fontStyle: "italic", marginBottom: 12, lineHeight: 1.5 }}>
                        "{alt.tradeoff_summary}"
                      </div>
                    )}

                    <div style={{ display: "flex", gap: 20, flexWrap: "wrap", fontSize: 12, color: "var(--text-secondary)" }}>
                      <span><span style={{ color: "var(--text-muted)" }}>Price: </span>${alt.unit_price_usd}/unit</span>
                      <span><span style={{ color: "var(--text-muted)" }}>Lead time: </span>{alt.lead_time_days}d</span>
                      {alt.on_time_rate != null && (
                        <span><span style={{ color: "var(--text-muted)" }}>On-time: </span>{Math.round(alt.on_time_rate * 100)}%</span>
                      )}
                      {alt.avg_review_rating != null && (
                        <span><span style={{ color: "var(--text-muted)" }}>Rating: </span>{Number(alt.avg_review_rating).toFixed(1)}</span>
                      )}
                    </div>
                  </div>

                  <div style={{ minWidth: 120 }}>
                    <ScoreBar value={alt.total_score || 0} max={1} label="Overall score" />
                    {alt.dynamic_reliability_score > 0 && (
                      <div style={{ marginTop: 8 }}>
                        <ScoreBar value={alt.dynamic_reliability_score} max={1} label="Reliability" />
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
