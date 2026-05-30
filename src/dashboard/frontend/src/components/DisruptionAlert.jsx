export default function DisruptionAlert({ disruption, severity }) {
  const severityColor = severity >= 8 ? "#ef4444"
                      : severity >= 6 ? "#f97316" : "#eab308"
  return (
    <div style={{
      background: "var(--bg-card)",
      border: `1px solid ${severityColor}40`,
      borderRadius: 16, padding: 24,
      boxShadow: `0 0 30px ${severityColor}15`
    }}>
      <div style={{
        display: "flex", alignItems: "center",
        gap: 8, marginBottom: 16
      }}>
        <span style={{ fontSize: 20 }}>🚨</span>
        <span style={{
          fontSize: 12, fontWeight: 700,
          color: severityColor, letterSpacing: 1,
          textTransform: "uppercase"
        }}>
          Active Disruption
        </span>
      </div>

      <p style={{
        fontSize: 15, fontWeight: 600,
        color: "var(--text-primary)", lineHeight: 1.5,
        marginBottom: 16
      }}>
        {disruption?.headline || "No headline"}
      </p>

      <div style={{
        display: "flex", alignItems: "center",
        justifyContent: "space-between"
      }}>
        <span style={{ fontSize: 13, color: "var(--text-secondary)" }}>
          📍 {disruption?.location_name || "Unknown"}
        </span>
        <div style={{
          background: `${severityColor}20`,
          border: `1px solid ${severityColor}40`,
          borderRadius: 8, padding: "4px 12px",
          fontSize: 13, fontWeight: 700, color: severityColor
        }}>
          Severity {severity}/10
        </div>
      </div>
    </div>
  )
}