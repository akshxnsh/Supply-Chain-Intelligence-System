export default function Header() {
  return (
    <header style={{
      background: "#0d1526",
      borderBottom: "1px solid #1e2d45",
      padding: "16px 32px",
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between"
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <div style={{
          width: 36, height: 36, borderRadius: 8,
          background: "linear-gradient(135deg, #3b82f6, #6366f1)",
          display: "flex", alignItems: "center",
          justifyContent: "center", fontSize: 18
        }}>🔔</div>
        <div>
          <div style={{
            fontWeight: 700, fontSize: 16,
            color: "var(--text-primary)"
          }}>
            Supply Chain Intelligence
          </div>
          <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>
            Lone Star Roofing Supply · demo-business-001
          </div>
        </div>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <div style={{
          width: 8, height: 8, borderRadius: "50%",
          background: "#22c55e",
          boxShadow: "0 0 8px #22c55e"
        }} />
        <span style={{ fontSize: 13, color: "var(--text-secondary)" }}>
          Agent Active
        </span>
      </div>
    </header>
  )
}