export default function ExposureCard({ exposure, supplier }) {
  const formatted = new Intl.NumberFormat("en-US", {
    style: "currency", currency: "USD", maximumFractionDigits: 0
  }).format(exposure) // Show at-risk total, not 8% loss

  return (
    <div style={{
      background: "var(--bg-card)",
      border: "1px solid #1e2d45",
      borderRadius: 16, padding: 24
    }}>
      <div style={{
        fontSize: 12, fontWeight: 700,
        color: "var(--text-secondary)",
        letterSpacing: 1, textTransform: "uppercase",
        marginBottom: 16
      }}>
        💰 Financial Exposure
      </div>

      <div style={{
        fontSize: 42, fontWeight: 800,
        color: "#ef4444", marginBottom: 8,
        letterSpacing: -1
      }}>
        {formatted}
      </div>

      <div style={{
        fontSize: 13, color: "var(--text-secondary)",
        marginBottom: 20
      }}>
        Total orders at risk across affected suppliers
      </div>

      {supplier?.name && (
        <div style={{
          background: "#0d1f12",
          border: "1px solid #22c55e30",
          borderRadius: 10, padding: "12px 16px",
          display: "flex", alignItems: "center", gap: 10
        }}>
          <span style={{ fontSize: 18 }}>✅</span>
          <div>
            <div style={{
              fontSize: 13, fontWeight: 700,
              color: "#22c55e"
            }}>
              Alternative Found
            </div>
            <div style={{
              fontSize: 12, color: "var(--text-secondary)"
            }}>
              {supplier.name} · {supplier.country}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}