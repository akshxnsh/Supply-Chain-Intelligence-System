import { useState, useEffect } from "react"

const API = "http://localhost:8000"

function getSeverityColor(score) {
  if (score >= 8) return "#ef4444"
  if (score >= 5) return "#f97316"
  return "#eab308"
}

function getSeverityLabel(score) {
  if (score >= 8) return "CRITICAL"
  if (score >= 5) return "ELEVATED"
  return "MODERATE"
}

function formatExposure(usd) {
  if (usd == null) return "$0"
  return "$" + Number(usd).toLocaleString("en-US")
}

function timeAgo(dateStr) {
  const diff = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000)
  if (diff < 60) return `${diff}s ago`
  const mins = Math.floor(diff / 60)
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

export default function OverviewScreen() {
  const [alerts, setAlerts] = useState([])
  const [totalExposure, setTotalExposure] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    async function fetchAll() {
      try {
        const res = await fetch(`${API}/api/alerts/all?limit=50`)
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const data = await res.json()
        setAlerts(data.alerts || [])
        setTotalExposure(data.total_exposure || 0)
        setError(null)
      } catch (err) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }
    fetchAll()
    const interval = setInterval(fetchAll, 30000)
    return () => clearInterval(interval)
  }, [])

  // Group alerts by business_id
  const grouped = alerts.reduce((acc, a) => {
    const biz = a.business_id || "unknown"
    if (!acc[biz]) acc[biz] = []
    acc[biz].push(a)
    return acc
  }, {})

  const activeCount = alerts.filter(a => a.status === "active").length

  return (
    <div style={{ maxWidth: 960, margin: "0 auto", padding: "40px 32px" }}>
      {/* Header */}
      <div style={{ marginBottom: 32 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, color: "var(--text-primary)", margin: 0, display: "flex", alignItems: "center", gap: 10 }}>
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none"
            stroke="var(--accent-blue)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" />
            <line x1="2" y1="12" x2="22" y2="12" />
            <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
          </svg>
          Overview
        </h1>
        <p style={{ fontSize: 14, color: "var(--text-secondary)", marginTop: 6 }}>
          Active disruption alerts across all registered businesses
        </p>
      </div>

      {/* Summary cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16, marginBottom: 32 }}>
        {[
          { label: "Total Alerts", value: alerts.length, color: "#60a5fa" },
          { label: "Active Alerts", value: activeCount, color: "#ef4444" },
          { label: "Total Exposure", value: formatExposure(totalExposure), color: "#f97316" },
        ].map(({ label, value, color }) => (
          <div key={label} style={{
            background: "var(--bg-card)", border: "1px solid var(--border)",
            borderRadius: 12, padding: "20px 24px",
          }}>
            <div style={{ fontSize: 12, color: "var(--text-muted)", fontWeight: 500, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 8 }}>
              {label}
            </div>
            <div style={{ fontSize: 26, fontWeight: 700, color }}>
              {loading ? "—" : value}
            </div>
          </div>
        ))}
      </div>

      {/* Alerts by business */}
      {loading && (
        <div style={{ color: "var(--text-muted)", fontSize: 14, textAlign: "center", padding: 40 }}>
          Loading alerts…
        </div>
      )}

      {error && (
        <div style={{ color: "#ef4444", fontSize: 14, padding: 16 }}>
          Error loading alerts: {error}
        </div>
      )}

      {!loading && alerts.length === 0 && (
        <div style={{
          background: "var(--bg-card)", border: "1px solid var(--border)",
          borderRadius: 12, padding: "60px 32px", textAlign: "center",
        }}>
          <div style={{ marginBottom: 12, display: "flex", justifyContent: "center" }}>
            <svg width="36" height="36" viewBox="0 0 24 24" fill="none"
              stroke="#22c55e" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
              <polyline points="22 4 12 14.01 9 11.01" />
            </svg>
          </div>
          <div style={{ fontSize: 16, fontWeight: 600, color: "var(--text-primary)" }}>
            No active alerts across any business
          </div>
        </div>
      )}

      {!loading && Object.entries(grouped).map(([bizId, bizAlerts]) => (
        <div key={bizId} style={{ marginBottom: 32 }}>
          {/* Business group header */}
          <div style={{
            display: "flex", alignItems: "center", gap: 10,
            marginBottom: 12,
          }}>
            <span style={{
              background: "rgba(59,130,246,0.1)", color: "#3b82f6",
              fontSize: 12, fontWeight: 600, padding: "3px 10px",
              borderRadius: 6, border: "1px solid rgba(59,130,246,0.2)",
            }}>
              {bizId}
            </span>
            <span style={{ color: "var(--text-muted)", fontSize: 13 }}>
              {bizAlerts.length} alert{bizAlerts.length !== 1 ? "s" : ""}
            </span>
          </div>

          {/* Alert rows */}
          {bizAlerts.map(a => {
            const color = getSeverityColor(a.severity_score)
            const label = getSeverityLabel(a.severity_score)
            return (
              <div key={a.id} style={{
                display: "flex", alignItems: "center", gap: 16,
                background: "var(--bg-card)", border: "1px solid var(--border)",
                borderLeft: `3px solid ${color}`, borderRadius: 10,
                padding: "14px 18px", marginBottom: 8,
              }}>
                <span style={{
                  background: color + "22", color, fontSize: 11, fontWeight: 700,
                  padding: "2px 8px", borderRadius: 20, border: `1px solid ${color}40`,
                  minWidth: 72, textAlign: "center",
                }}>
                  {label}
                </span>
                <span style={{ fontSize: 18, fontWeight: 700, color: "var(--text-primary)", minWidth: 120 }}>
                  {formatExposure(a.exposure_usd)}
                </span>
                <span style={{ fontSize: 13, color: "var(--text-secondary)" }}>
                  Severity: <span style={{ color, fontWeight: 600 }}>{Number(a.severity_score).toFixed(1)}</span>/10
                </span>
                <span style={{ fontSize: 12, color: "var(--text-muted)", marginLeft: "auto" }}>
                  {timeAgo(a.created_at)}
                </span>
                <span style={{
                  fontSize: 11, fontWeight: 600, padding: "2px 8px", borderRadius: 20,
                  background: a.status === "acknowledged" ? "rgba(59,130,246,0.15)" : "rgba(239,68,68,0.15)",
                  color: a.status === "acknowledged" ? "#3b82f6" : "#ef4444",
                  textTransform: "capitalize",
                }}>
                  {a.status || "active"}
                </span>
              </div>
            )
          })}
        </div>
      ))}
    </div>
  )
}
