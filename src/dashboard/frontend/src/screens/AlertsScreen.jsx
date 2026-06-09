import { useState, useEffect, useCallback } from "react";

function getSeverityColor(score) {
  if (score >= 8) return "#ef4444";
  if (score >= 5) return "#f97316";
  return "#eab308";
}

function getSeverityLabel(score) {
  if (score >= 8) return "CRITICAL";
  if (score >= 5) return "ELEVATED";
  return "MODERATE";
}

function formatExposure(usd) {
  if (usd == null) return "$0";
  return "$" + Number(usd).toLocaleString("en-US");
}

function timeAgo(dateStr) {
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const diff = Math.floor((now - then) / 1000);
  if (diff < 10) return "just now";
  if (diff < 60) return `${diff} seconds ago`;
  const mins = Math.floor(diff / 60);
  if (mins < 60) return `${mins} minute${mins !== 1 ? "s" : ""} ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} hour${hours !== 1 ? "s" : ""} ago`;
  const days = Math.floor(hours / 24);
  return `${days} day${days !== 1 ? "s" : ""} ago`;
}

function SkeletonRow() {
  return (
    <div
      style={{
        height: 72,
        borderRadius: 12,
        marginBottom: 12,
        background: "linear-gradient(90deg, #111827 25%, #1a2234 50%, #111827 75%)",
        backgroundSize: "200% 100%",
        animation: "shimmer 1.4s infinite",
      }}
    />
  );
}

function AlertCard({ alert, onAcknowledge }) {
  const [expanded, setExpanded] = useState(false);
  const [hovered, setHovered] = useState(false);
  const [localStatus, setLocalStatus] = useState(alert.status);
  const color = getSeverityColor(alert.severity_score);
  const label = getSeverityLabel(alert.severity_score);

  const statusColors = {
    active: { bg: "rgba(239,68,68,0.15)", text: "#ef4444" },
    resolved: { bg: "rgba(34,197,94,0.15)", text: "#22c55e" },
    acknowledged: { bg: "rgba(59,130,246,0.15)", text: "#3b82f6" },
  };
  const statusStyle = statusColors[localStatus] || { bg: "rgba(148,163,184,0.15)", text: "#94a3b8" };

  const handleAcknowledge = async (e) => {
    e.stopPropagation();
    try {
      await fetch(`http://localhost:8000/api/alerts/${alert.id}/acknowledge`, { method: "POST" });
      setLocalStatus("acknowledged");
      if (onAcknowledge) onAcknowledge(alert.id);
    } catch {}
  };

  const severityBg =
    label === "CRITICAL"
      ? "rgba(239,68,68,0.15)"
      : label === "ELEVATED"
      ? "rgba(249,115,22,0.15)"
      : "rgba(234,179,8,0.15)";

  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: "flex",
        background: hovered ? "var(--bg-card-hover)" : "var(--bg-card)",
        border: "1px solid var(--border)",
        borderRadius: 12,
        marginBottom: 12,
        overflow: "hidden",
        transition: "all 0.15s ease",
        animation: "fadeIn 0.25s ease",
        cursor: "pointer",
      }}
      onClick={() => setExpanded((e) => !e)}
    >
      {/* Left severity bar */}
      <div style={{ width: 3, background: color, flexShrink: 0 }} />

      {/* Main content */}
      <div style={{ flex: 1, padding: "16px 20px" }}>
        {/* Top row */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span
              style={{
                background: severityBg,
                color: color,
                fontSize: 11,
                fontWeight: 700,
                letterSpacing: "0.08em",
                padding: "3px 10px",
                borderRadius: 20,
                border: `1px solid ${color}40`,
              }}
            >
              {label}
            </span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            {localStatus !== "acknowledged" && (
              <button
                onClick={handleAcknowledge}
                style={{
                  background: "#1e3a5f",
                  color: "#60a5fa",
                  border: "1px solid #2563eb44",
                  borderRadius: 8,
                  padding: "3px 10px",
                  fontSize: 11,
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                Acknowledge
              </button>
            )}
            <span
              style={{
                background: statusStyle.bg,
                color: statusStyle.text,
                fontSize: 11,
                fontWeight: 600,
                padding: "3px 10px",
                borderRadius: 20,
                textTransform: "capitalize",
              }}
            >
              {localStatus || "unknown"}
            </span>
            <span
              style={{
                color: "var(--text-muted)",
                fontSize: 18,
                transition: "transform 0.15s ease",
                transform: expanded ? "rotate(180deg)" : "rotate(0deg)",
                display: "inline-block",
                lineHeight: 1,
              }}
            >
              &#8964;
            </span>
          </div>
        </div>

        {/* Middle row */}
        <div style={{ display: "flex", alignItems: "baseline", gap: 16, marginBottom: 8 }}>
          <span style={{ fontSize: 22, fontWeight: 700, color: "var(--text-primary)" }}>
            {formatExposure(alert.exposure_usd)}
          </span>
          <span style={{ fontSize: 13, color: "var(--text-secondary)" }}>
            Severity:{" "}
            <span style={{ color: color, fontWeight: 600 }}>
              {Number(alert.severity_score).toFixed(1)}
            </span>{" "}
            / 10
          </span>
          {alert.calibration_confidence != null && (
            <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
              Model confidence:{" "}
              <span style={{ color: "#a78bfa", fontWeight: 600 }}>
                {Math.round(alert.calibration_confidence * 100)}%
              </span>
            </span>
          )}
        </div>

        {/* Bottom row */}
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span
            style={{
              background: "rgba(59,130,246,0.1)",
              color: "#3b82f6",
              fontSize: 11,
              fontWeight: 500,
              padding: "2px 8px",
              borderRadius: 6,
              border: "1px solid rgba(59,130,246,0.2)",
            }}
          >
            {alert.business_id}
          </span>
          <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
            {timeAgo(alert.created_at)}
          </span>
        </div>

        {/* Expanded JSON */}
        {expanded && (
          <div
            style={{ marginTop: 16 }}
            onClick={(e) => e.stopPropagation()}
          >
            <pre
              style={{
                background: "#0a0f1e",
                border: "1px solid var(--border)",
                borderRadius: 8,
                padding: "14px 16px",
                fontSize: 12,
                color: "var(--text-secondary)",
                overflowX: "auto",
                margin: 0,
                lineHeight: 1.6,
                fontFamily: "monospace",
              }}
            >
              {JSON.stringify(alert, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}

export default function AlertsScreen({ businessId }) {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [lastRefreshed, setLastRefreshed] = useState(null);
  const [error, setError] = useState(null);
  const [page, setPage] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const PAGE_SIZE = 10;

  const fetchAlerts = useCallback(async (pageNum = 0, append = false) => {
    try {
      const res = await fetch(
        `http://localhost:8000/api/alerts?business_id=${businessId}&limit=${PAGE_SIZE}&offset=${pageNum * PAGE_SIZE}`
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const newAlerts = data.alerts || [];
      setAlerts(prev => append ? [...prev, ...newAlerts] : newAlerts);
      setHasMore(newAlerts.length === PAGE_SIZE);
      setLastRefreshed(new Date());
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, [businessId]);

  useEffect(() => {
    setPage(0);
    setAlerts([]);
    setHasMore(true);
    setLoading(true);
    fetchAlerts(0, false);
    const interval = setInterval(() => fetchAlerts(0, false), 30000);
    return () => clearInterval(interval);
  }, [fetchAlerts]);

  const handleRefresh = () => {
    setPage(0);
    setLoading(true);
    fetchAlerts(0, false);
  };

  const handleLoadMore = () => {
    const nextPage = page + 1;
    setPage(nextPage);
    setLoadingMore(true);
    fetchAlerts(nextPage, true);
  };

  const totalExposure = alerts.reduce((sum, a) => sum + (a.exposure_usd || 0), 0);

  const formatTime = (date) => {
    if (!date) return "";
    return date.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  };

  return (
    <>
      <style>{`
        @keyframes shimmer {
          0% { background-position: 200% 0; }
          100% { background-position: -200% 0; }
        }
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(6px); }
          to { opacity: 1; transform: translateY(0); }
        }
      `}</style>

      <div
        style={{
          maxWidth: 960,
          margin: "0 auto",
          padding: "40px 32px",
        }}
      >
        {/* Page header */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: 32,
          }}
        >
          <h1
            style={{
              fontSize: 28,
              fontWeight: 700,
              color: "var(--text-primary)",
              margin: 0,
            }}
          >
            Active Alerts
          </h1>
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            {lastRefreshed && (
              <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
                Updated {formatTime(lastRefreshed)}
              </span>
            )}
            <button
              onClick={handleRefresh}
              style={{
                background: "transparent",
                border: "1px solid var(--border)",
                borderRadius: 8,
                color: "var(--text-secondary)",
                fontSize: 13,
                fontWeight: 500,
                padding: "7px 16px",
                cursor: "pointer",
                transition: "all 0.15s ease",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = "var(--bg-card-hover)";
                e.currentTarget.style.color = "var(--text-primary)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = "transparent";
                e.currentTarget.style.color = "var(--text-secondary)";
              }}
            >
              ↻ Refresh
            </button>
          </div>
        </div>

        {/* Error banner */}
        {error && (
          <div
            style={{
              background: "rgba(239,68,68,0.1)",
              border: "1px solid rgba(239,68,68,0.3)",
              borderRadius: 10,
              padding: "12px 18px",
              marginBottom: 20,
              color: "#ef4444",
              fontSize: 13,
            }}
          >
            Failed to load alerts: {error}
          </div>
        )}

        {/* Loading skeletons */}
        {loading && (
          <>
            <SkeletonRow />
            <SkeletonRow />
            <SkeletonRow />
          </>
        )}

        {/* Content */}
        {!loading && (
          <>
            {alerts.length === 0 ? (
              /* Empty state */
              <div
                style={{
                  background: "var(--bg-card)",
                  border: "1px solid var(--border)",
                  borderRadius: 12,
                  padding: "60px 32px",
                  textAlign: "center",
                }}
              >
                <div style={{ marginBottom: 16, display: "flex", justifyContent: "center" }}>
                  <svg width="40" height="40" viewBox="0 0 24 24" fill="none"
                    stroke="var(--text-muted)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
                    <path d="M13.73 21a2 2 0 0 1-3.46 0" />
                  </svg>
                </div>
                <div
                  style={{
                    fontSize: 18,
                    fontWeight: 600,
                    color: "var(--text-primary)",
                    marginBottom: 10,
                  }}
                >
                  No active alerts
                </div>
                <div
                  style={{
                    fontSize: 14,
                    color: "var(--text-secondary)",
                    maxWidth: 420,
                    margin: "0 auto",
                    lineHeight: 1.6,
                  }}
                >
                  The agent is monitoring your supply chain — alerts will appear here when disruptions are detected.
                </div>
              </div>
            ) : (
              <>
                {/* Summary row */}
                <div
                  style={{
                    fontSize: 13,
                    color: "var(--text-muted)",
                    marginBottom: 16,
                  }}
                >
                  <span style={{ color: "var(--text-secondary)", fontWeight: 500 }}>
                    {alerts.length} alert{alerts.length !== 1 ? "s" : ""}
                  </span>
                  {" · "}
                  <span style={{ color: "var(--text-secondary)", fontWeight: 500 }}>
                    {formatExposure(totalExposure)}
                  </span>{" "}
                  total exposure at risk
                </div>

                {/* Alert cards */}
                {alerts.map((alert) => (
                  <AlertCard
                    key={alert.id}
                    alert={alert}
                    onAcknowledge={(id) =>
                      setAlerts(prev => prev.map(a => a.id === id ? { ...a, status: "acknowledged" } : a))
                    }
                  />
                ))}

                {/* Load More */}
                {hasMore && (
                  <div style={{ textAlign: "center", marginTop: 16 }}>
                    <button
                      onClick={handleLoadMore}
                      disabled={loadingMore}
                      style={{
                        background: "#111827",
                        color: loadingMore ? "var(--text-muted)" : "#60a5fa",
                        border: "1px solid #1e2d45",
                        borderRadius: 8,
                        padding: "8px 24px",
                        fontSize: 13,
                        fontWeight: 500,
                        cursor: loadingMore ? "default" : "pointer",
                      }}
                    >
                      {loadingMore ? "Loading…" : "Load More"}
                    </button>
                  </div>
                )}
              </>
            )}
          </>
        )}
      </div>
    </>
  );
}
