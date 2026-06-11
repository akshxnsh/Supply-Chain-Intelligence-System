import { useState, useEffect, useCallback } from "react"

import { API } from "../config";
function formatAge(minutes) {
  if (minutes == null) return "—"
  if (minutes < 1) return "< 1 min ago"
  if (minutes < 60) return `${Math.round(minutes)} min ago`
  const h = Math.floor(minutes / 60)
  const m = Math.round(minutes % 60)
  return m > 0 ? `${h}h ${m}m ago` : `${h}h ago`
}

function formatTime(isoStr) {
  if (!isoStr) return "—"
  const d = new Date(isoStr)
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
}

// health = min(100, threshold / age * 100)
// 100% = perfectly fresh, decreases as staleness grows
function healthPct(age, max) {
  if (!age || age <= 0) return 100
  return Math.min(100, Math.round((max / age) * 100))
}

function healthColor(pct) {
  if (pct >= 80) return "#22c55e"
  if (pct >= 40) return "#f97316"
  return "#ef4444"
}

function HealthBar({ age, max }) {
  const pct = healthPct(age, max)
  const color = healthColor(pct)
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <div style={{
        width: 100, height: 6, borderRadius: 4,
        background: "var(--border)", overflow: "hidden",
      }}>
        <div style={{
          width: `${pct}%`, height: "100%",
          background: color, borderRadius: 4,
          transition: "width 0.4s ease",
        }} />
      </div>
      <span style={{ fontSize: 11, color, fontWeight: 600, minWidth: 32 }}>{pct}%</span>
    </div>
  )
}

function TableRow({ row, onRefresh, refreshing }) {
  const isStale = row.is_stale
  const borderColor = isStale ? "#f97316" : "#22c55e"
  const statusIcon = isStale ? "⚠️" : "✅"

  return (
    <div style={{
      background: "var(--bg-card)",
      border: `1px solid var(--border)`,
      borderLeft: `3px solid ${borderColor}`,
      borderRadius: 10,
      padding: "14px 18px",
      marginBottom: 8,
      display: "flex",
      alignItems: "center",
      gap: 16,
      flexWrap: "wrap",
    }}>
      {/* Status + name */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 220 }}>
        <span style={{ fontSize: 16 }}>{statusIcon}</span>
        <span style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)", fontFamily: "monospace" }}>
          {row.table_name}
        </span>
      </div>

      {/* Age */}
      <div style={{ minWidth: 120 }}>
        <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 2 }}>Age</div>
        <div style={{ fontSize: 13, color: isStale ? "#f97316" : "var(--text-secondary)", fontWeight: 500 }}>
          {formatAge(row.age_minutes)}
        </div>
      </div>

      {/* Health bar */}
      <div style={{ minWidth: 160 }}>
        <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 4 }}>Health</div>
        <HealthBar age={row.age_minutes} max={row.max_age_minutes} />
      </div>

      {/* Last sync */}
      <div style={{ minWidth: 110 }}>
        <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 2 }}>Last sync</div>
        <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>
          {formatTime(row.last_modified)}
        </div>
      </div>

      {/* Refresh button — only for stale tables */}
      <div style={{ marginLeft: "auto" }}>
        {isStale && (
          <button
            onClick={() => onRefresh(row.table_name)}
            disabled={refreshing}
            style={{
              background: refreshing ? "var(--bg-card)" : "rgba(249,115,22,0.1)",
              border: "1px solid rgba(249,115,22,0.4)",
              borderRadius: 8,
              color: refreshing ? "var(--text-muted)" : "#f97316",
              fontSize: 12,
              fontWeight: 600,
              padding: "6px 14px",
              cursor: refreshing ? "not-allowed" : "pointer",
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            {refreshing ? (
              <>
                <span style={{
                  width: 10, height: 10, borderRadius: "50%",
                  border: "2px solid var(--text-muted)",
                  borderTopColor: "#f97316",
                  display: "inline-block",
                  animation: "spin 0.8s linear infinite",
                }} />
                Refreshing…
              </>
            ) : "Refresh Now"}
          </button>
        )}
      </div>
    </div>
  )
}

export default function FreshnessScreen() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [refreshing, setRefreshing] = useState({}) // table_name -> bool

  const fetchFreshness = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/freshness`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setData(await res.json())
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchFreshness()
    const interval = setInterval(fetchFreshness, 60000) // 60s poll
    return () => clearInterval(interval)
  }, [fetchFreshness])

  async function handleRefresh(tableName) {
    setRefreshing(r => ({ ...r, [tableName]: true }))
    try {
      await fetch(`${API}/api/freshness/refresh/${tableName}`, { method: "POST" })
      await fetchFreshness()
    } catch (err) {
      console.error("Refresh failed:", err)
    } finally {
      setRefreshing(r => ({ ...r, [tableName]: false }))
    }
  }

  async function handleRefreshAllStale() {
    const stale = (data?.tables || []).filter(t => t.is_stale)
    for (const t of stale) {
      await handleRefresh(t.table_name)
    }
  }

  // Sort: stale first, then by age descending
  const tables = [...(data?.tables || [])].sort((a, b) => {
    if (a.is_stale !== b.is_stale) return a.is_stale ? -1 : 1
    return (b.age_minutes || 0) - (a.age_minutes || 0)
  })

  const staleCount = tables.filter(t => t.is_stale).length
  const freshPct = data?.freshness_pct ?? 0
  const freshColor = freshPct >= 90 ? "#22c55e" : freshPct >= 70 ? "#f97316" : "#ef4444"

  return (
    <div style={{ maxWidth: 960, margin: "0 auto", padding: "40px 32px" }}>
      {/* Header */}
      <div style={{ marginBottom: 28 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>
          Data Freshness Monitor
        </h1>
        <p style={{ fontSize: 14, color: "var(--text-secondary)", marginTop: 6 }}>
          Real-time freshness status for all configured BigQuery tables
        </p>
      </div>

      {/* Summary bar */}
      {!loading && data && (
        <div style={{
          display: "flex", alignItems: "center", gap: 24,
          background: "var(--bg-card)", border: "1px solid var(--border)",
          borderRadius: 12, padding: "16px 24px", marginBottom: 24,
          flexWrap: "wrap",
        }}>
          <div>
            <div style={{ fontSize: 11, color: "var(--text-muted)", fontWeight: 500, textTransform: "uppercase", letterSpacing: "0.06em" }}>Tables</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: "var(--text-primary)" }}>{data.total_count}</div>
          </div>
          <div style={{ width: 1, height: 36, background: "var(--border)" }} />
          <div>
            <div style={{ fontSize: 11, color: "var(--text-muted)", fontWeight: 500, textTransform: "uppercase", letterSpacing: "0.06em" }}>Fresh</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: "#22c55e" }}>{data.fresh_count}</div>
          </div>
          <div style={{ width: 1, height: 36, background: "var(--border)" }} />
          <div>
            <div style={{ fontSize: 11, color: "var(--text-muted)", fontWeight: 500, textTransform: "uppercase", letterSpacing: "0.06em" }}>Stale</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: staleCount > 0 ? "#f97316" : "#22c55e" }}>{staleCount}</div>
          </div>
          <div style={{ width: 1, height: 36, background: "var(--border)" }} />
          <div>
            <div style={{ fontSize: 11, color: "var(--text-muted)", fontWeight: 500, textTransform: "uppercase", letterSpacing: "0.06em" }}>Overall Health</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: freshColor }}>{freshPct}%</div>
          </div>
          {staleCount > 0 && (
            <div style={{ marginLeft: "auto" }}>
              <button
                onClick={handleRefreshAllStale}
                style={{
                  background: "rgba(249,115,22,0.1)",
                  border: "1px solid rgba(249,115,22,0.4)",
                  borderRadius: 8,
                  color: "#f97316",
                  fontSize: 13,
                  fontWeight: 600,
                  padding: "8px 18px",
                  cursor: "pointer",
                }}
              >
                Refresh All Stale ({staleCount})
              </button>
            </div>
          )}
        </div>
      )}

      {loading && (
        <div style={{ color: "var(--text-muted)", fontSize: 14, textAlign: "center", padding: 60 }}>
          Loading freshness data…
        </div>
      )}

      {error && (
        <div style={{
          background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.3)",
          borderRadius: 10, padding: "14px 18px", color: "#ef4444", fontSize: 14, marginBottom: 16,
        }}>
          Error loading freshness data: {error}
        </div>
      )}

      {/* Table rows */}
      {!loading && tables.map(row => (
        <TableRow
          key={row.table_name}
          row={row}
          onRefresh={handleRefresh}
          refreshing={!!refreshing[row.table_name]}
        />
      ))}

      {/* Spin keyframe injected via style tag */}
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  )
}
