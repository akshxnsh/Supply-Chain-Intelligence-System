import { useState, useEffect } from "react"

import { API } from "../config";
function formatExposure(usd) {
  if (!usd) return "$0"
  if (usd >= 1_000_000) return `$${(usd / 1_000_000).toFixed(1)}M`
  if (usd >= 1_000) return `$${Math.round(usd / 1_000)}K`
  return `$${Number(usd).toLocaleString("en-US")}`
}

function timeAgo(dateStr) {
  if (!dateStr) return null
  const diff = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000)
  if (diff < 60) return `${diff}s ago`
  const mins = Math.floor(diff / 60)
  if (mins < 60) return `${mins} min ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

function freshnessBadgeColor(pct) {
  if (pct >= 90) return { bg: "rgba(34,197,94,0.12)", color: "#22c55e", border: "rgba(34,197,94,0.3)" }
  if (pct >= 70) return { bg: "rgba(249,115,22,0.12)", color: "#f97316", border: "rgba(249,115,22,0.3)" }
  return { bg: "rgba(239,68,68,0.12)", color: "#ef4444", border: "rgba(239,68,68,0.3)" }
}

function freshnessIcon(pct) {
  if (pct >= 90) return "🟢"
  if (pct >= 70) return "🟡"
  return "🔴"
}

function confidenceColor(pct) {
  if (pct >= 80) return "#22c55e"
  if (pct >= 60) return "#f97316"
  return "#ef4444"
}

export default function DashboardScreen({ businessId, businessName, onNavigate, refreshKey }) {
  const [alerts, setAlerts]       = useState([])
  const [analysis, setAnalysis]   = useState(null)
  const [freshness, setFreshness] = useState(null)
  const [loading, setLoading]     = useState(true)

  useEffect(() => {
    async function fetchAll() {
      setLoading(true)
      try {
        const [alertsRes, analysisRes, freshnessRes] = await Promise.all([
          fetch(`${API}/api/alerts/all?limit=50`).then(r => r.ok ? r.json() : { alerts: [] }),
          fetch(`${API}/api/latest-analysis?business_id=${businessId}`).then(r => r.ok ? r.json() : null),
          fetch(`${API}/api/freshness`).then(r => r.ok ? r.json() : { tables: [], freshness_pct: 0 }),
        ])
        setAlerts(alertsRes.alerts || [])
        setAnalysis(analysisRes)
        setFreshness(freshnessRes)
      } finally {
        setLoading(false)
      }
    }
    fetchAll()
  }, [businessId, refreshKey])

  const critical = alerts.filter(a => (a.severity_score || 0) >= 8)
  const medium   = alerts.filter(a => (a.severity_score || 0) >= 5 && (a.severity_score || 0) < 8)
  const totalExposure = alerts.reduce((s, a) => s + (a.exposure_usd || 0), 0)
  const lastAlert = alerts[0]
  const freshPct = freshness?.freshness_pct ?? null
  const stale4 = (freshness?.tables || [])
    .sort((a, b) => (b.age_minutes || 0) - (a.age_minutes || 0))
    .slice(0, 4)

  const hasAnalysis = analysis?.has_result
  const headline = analysis?.headline || ""
  const region   = analysis?.disruption_region || ""
  const affectedName = (analysis?.affected_suppliers?.[0]?.name) || (analysis?.affected_suppliers?.[0]?.supplier_id) || ""
  const confidence = Math.round((analysis?.calibration_confidence || 0) * 100)
  const severity  = Number(analysis?.severity_score || 0).toFixed(1)

  // Build AI summary sentence
  let summaryText = null
  if (hasAnalysis && headline) {
    summaryText = headline
    if (region && !headline.toLowerCase().includes(region.toLowerCase())) {
      summaryText += ` (${region})`
    }
    if (confidence > 0) summaryText += `. Confidence: ${confidence}%.`
  }

  const allHealthy = alerts.length === 0

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto", padding: "32px 32px" }}>

      {/* Dashboard header */}
      <div style={{
        display: "flex", alignItems: "flex-start", justifyContent: "space-between",
        marginBottom: 28, flexWrap: "wrap", gap: 12,
      }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>
            Supply Chain Intelligence
          </h1>
          <div style={{ display: "flex", gap: 16, marginTop: 6, flexWrap: "wrap" }}>
            {lastAlert?.created_at && (
              <span style={{ fontSize: 13, color: "var(--text-secondary)" }}>
                Last Analysis: <strong>{timeAgo(lastAlert.created_at)}</strong>
              </span>
            )}
            {businessName && (
              <span style={{ fontSize: 13, color: "var(--text-secondary)" }}>
                {businessName}
              </span>
            )}
          </div>
        </div>

        {/* Data freshness badge */}
        {freshPct !== null && (() => {
          const fc = freshnessBadgeColor(freshPct)
          return (
            <div style={{
              background: fc.bg, border: `1px solid ${fc.border}`,
              borderRadius: 10, padding: "10px 18px",
              display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 2,
            }}>
              <div style={{ fontSize: 11, color: "var(--text-muted)", fontWeight: 500, textTransform: "uppercase", letterSpacing: "0.06em" }}>
                Data Freshness
              </div>
              <div style={{ fontSize: 20, fontWeight: 700, color: fc.color }}>
                {freshnessIcon(freshPct)} {freshPct}%
              </div>
            </div>
          )
        })()}
      </div>

      {/* Executive Status Cards */}
      {allHealthy && !loading ? (
        <div style={{
          background: "rgba(34,197,94,0.06)", border: "1px solid rgba(34,197,94,0.3)",
          borderRadius: 14, padding: "28px 32px", marginBottom: 28,
          display: "flex", alignItems: "center", gap: 20,
        }}>
          <div style={{
            width: 10, height: 10, borderRadius: "50%", background: "#22c55e", flexShrink: 0,
            boxShadow: "0 0 8px rgba(34,197,94,0.6)",
          }} />
          <div>
            <div style={{ fontSize: 15, fontWeight: 600, color: "var(--text-primary)" }}>
              No Active Disruptions
            </div>
            <div style={{ fontSize: 13, color: "var(--text-secondary)", marginTop: 2 }}>
              All monitored suppliers and routes are operating within normal parameters.
            </div>
          </div>
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16, marginBottom: 28 }}>
          {/* Critical */}
          <div style={{
            background: "var(--bg-card)",
            border: "1px solid var(--border)",
            borderLeft: "3px solid #ef4444",
            borderRadius: 14, padding: "20px 24px",
            boxShadow: critical.length > 0 ? "0 0 12px rgba(239,68,68,0.2)" : "none",
          }}>
            <div style={{ fontSize: 11, color: "#ef4444", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 8 }}>
              🔴 Critical
            </div>
            <div style={{ fontSize: 36, fontWeight: 800, color: critical.length > 0 ? "#ef4444" : "var(--text-primary)" }}>
              {loading ? "—" : critical.length}
            </div>
            <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>alerts</div>
          </div>

          {/* Medium */}
          <div style={{
            background: "var(--bg-card)",
            border: "1px solid var(--border)",
            borderLeft: "3px solid #f97316",
            borderRadius: 14, padding: "20px 24px",
          }}>
            <div style={{ fontSize: 11, color: "#f97316", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 8 }}>
              🟡 Medium
            </div>
            <div style={{ fontSize: 36, fontWeight: 800, color: medium.length > 0 ? "#f97316" : "var(--text-primary)" }}>
              {loading ? "—" : medium.length}
            </div>
            <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>risks</div>
          </div>

          {/* Exposure */}
          <div style={{
            background: "var(--bg-card)",
            border: "1px solid var(--border)",
            borderLeft: "3px solid #60a5fa",
            borderRadius: 14, padding: "20px 24px",
          }}>
            <div style={{ fontSize: 11, color: "#60a5fa", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 8 }}>
              💰 Exposure
            </div>
            <div style={{ fontSize: 36, fontWeight: 800, color: totalExposure > 0 ? "#f97316" : "var(--text-primary)" }}>
              {loading ? "—" : formatExposure(totalExposure)}
            </div>
            <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>potential loss</div>
          </div>
        </div>
      )}

      {/* AI Intelligence Summary */}
      <div style={{
        background: "rgba(59,130,246,0.06)", border: "1px solid rgba(59,130,246,0.2)",
        borderRadius: 12, padding: "18px 22px", marginBottom: 28,
      }}>
        <div style={{
          fontSize: 11, color: "#60a5fa", fontWeight: 600,
          textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 8,
        }}>
          AI Intelligence Summary
        </div>
        {loading ? (
          <div style={{ fontSize: 14, color: "var(--text-muted)" }}>Loading…</div>
        ) : summaryText ? (
          <div style={{ fontSize: 15, color: "var(--text-primary)", lineHeight: 1.6 }}>
            {summaryText}
            {confidence > 0 && (
              <span style={{ marginLeft: 10, fontSize: 13, color: confidenceColor(confidence), fontWeight: 600 }}>
                {confidence}% confidence
              </span>
            )}
          </div>
        ) : (
          <div style={{ fontSize: 14, color: "var(--text-muted)", fontStyle: "italic" }}>
            Run a simulation to see the agent's analysis.
          </div>
        )}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24, alignItems: "start" }}>

        {/* Active Risk Cards */}
        <div>
          <div style={{
            display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14,
          }}>
            <h2 style={{ fontSize: 15, fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>Active Risks</h2>
            <button
              onClick={() => onNavigate && onNavigate("risks")}
              style={{
                background: "none", border: "none", color: "#60a5fa",
                fontSize: 13, cursor: "pointer", padding: 0,
              }}
            >
              View all →
            </button>
          </div>

          {loading ? (
            <div style={{ color: "var(--text-muted)", fontSize: 13, padding: 16 }}>Loading…</div>
          ) : !hasAnalysis ? (
            <div style={{
              background: "var(--bg-card)", border: "1px solid var(--border)",
              borderRadius: 10, padding: "24px 20px", textAlign: "center",
              color: "var(--text-muted)", fontSize: 13,
            }}>
              Run a simulation to see active risks.
            </div>
          ) : (
            <>
              {/* Top-level disruption card */}
              <div style={{
                background: "var(--bg-card)",
                border: "1px solid var(--border)",
                borderLeft: `3px solid ${Number(severity) >= 8 ? "#ef4444" : Number(severity) >= 5 ? "#f97316" : "#eab308"}`,
                borderRadius: 10, padding: "16px 18px", marginBottom: 10,
              }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
                  <span style={{
                    fontSize: 11, fontWeight: 700,
                    color: Number(severity) >= 8 ? "#ef4444" : "#f97316",
                    textTransform: "uppercase", letterSpacing: "0.06em",
                  }}>
                    {Number(severity) >= 8 ? "HIGH RISK" : Number(severity) >= 5 ? "ELEVATED" : "MODERATE"}
                  </span>
                  <span style={{ fontSize: 18, fontWeight: 800, color: "var(--text-primary)" }}>
                    {Math.round(Number(severity) * 10)}/100
                  </span>
                </div>
                {affectedName && (
                  <div style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 4 }}>
                    <span style={{ color: "var(--text-muted)" }}>Supplier: </span>{affectedName}
                  </div>
                )}
                {headline && (
                  <div style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 10 }}>
                    <span style={{ color: "var(--text-muted)" }}>Reason: </span>{headline}
                  </div>
                )}
                {confidence > 0 && (
                  <div style={{ fontSize: 12, color: confidenceColor(confidence) }}>
                    Confidence: {confidence}%
                  </div>
                )}
                <div style={{ marginTop: 12, textAlign: "right" }}>
                  <button
                    onClick={() => onNavigate && onNavigate("risks")}
                    style={{
                      background: "rgba(96,165,250,0.1)", border: "1px solid rgba(96,165,250,0.3)",
                      borderRadius: 7, color: "#60a5fa", fontSize: 12, fontWeight: 600,
                      padding: "5px 12px", cursor: "pointer",
                    }}
                  >
                    Details →
                  </button>
                </div>
              </div>

              {/* Alternative supplier cards (top 2) */}
              {(analysis?.suggested_alternatives || []).slice(0, 2).map((alt, i) => (
                <div key={i} style={{
                  background: "var(--bg-card)", border: "1px solid var(--border)",
                  borderRadius: 10, padding: "14px 18px", marginBottom: 10,
                  display: "flex", justifyContent: "space-between", alignItems: "center",
                }}>
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)" }}>
                      #{alt.rank} {alt.name}
                    </div>
                    <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>
                      {alt.country} · {alt.lead_time_days}d lead · ${alt.unit_price_usd}/unit
                    </div>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div style={{ fontSize: 13, fontWeight: 700, color: "#22c55e" }}>
                      {Math.round((alt.total_score || 0) * 100)}%
                    </div>
                    <div style={{ fontSize: 11, color: "var(--text-muted)" }}>score</div>
                  </div>
                </div>
              ))}
            </>
          )}
        </div>

        {/* Data Freshness Widget */}
        <div>
          <div style={{
            display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14,
          }}>
            <h2 style={{ fontSize: 15, fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>Data Freshness</h2>
            <button
              onClick={() => onNavigate && onNavigate("freshness")}
              style={{
                background: "none", border: "none", color: "#60a5fa",
                fontSize: 13, cursor: "pointer", padding: 0,
              }}
            >
              View all →
            </button>
          </div>

          {loading ? (
            <div style={{ color: "var(--text-muted)", fontSize: 13, padding: 16 }}>Loading…</div>
          ) : stale4.length === 0 && (freshness?.tables || []).length === 0 ? (
            <div style={{
              background: "var(--bg-card)", border: "1px solid var(--border)",
              borderRadius: 10, padding: "24px 20px", textAlign: "center",
              color: "var(--text-muted)", fontSize: 13,
            }}>
              No freshness data available.
            </div>
          ) : (
            (freshness?.tables || [])
              .sort((a, b) => (b.age_minutes || 0) - (a.age_minutes || 0))
              .slice(0, 4)
              .map(row => {
                const isStale = row.is_stale
                return (
                  <div key={row.table_name} style={{
                    background: "var(--bg-card)", border: "1px solid var(--border)",
                    borderLeft: `3px solid ${isStale ? "#f97316" : "#22c55e"}`,
                    borderRadius: 10, padding: "12px 16px", marginBottom: 8,
                    display: "flex", alignItems: "center", justifyContent: "space-between",
                  }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ fontSize: 14 }}>{isStale ? "⚠️" : "✅"}</span>
                      <span style={{ fontSize: 13, fontWeight: 500, color: "var(--text-primary)", fontFamily: "monospace" }}>
                        {row.table_name}
                      </span>
                    </div>
                    <div style={{ fontSize: 12, color: isStale ? "#f97316" : "var(--text-muted)", fontWeight: isStale ? 600 : 400 }}>
                      {Math.round(row.age_minutes || 0)} min ago
                    </div>
                  </div>
                )
              })
          )}
        </div>
      </div>
    </div>
  )
}
