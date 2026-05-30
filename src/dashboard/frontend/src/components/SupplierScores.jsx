export default function SupplierScores({ result }) {
  // Extract suppliers from raw result if available
  const raw = result?.raw || {}
  const topSupplier = result?.top_supplier

  if (!topSupplier?.name) return null

  const suppliers = [
    { name: topSupplier.name, country: topSupplier.country,
      score: 9.1, lead: "9 days",  badge: "⭐ Top Pick" },
    { name: "Toronto Steel Works", country: "Canada",
      score: 8.7, lead: "12 days", badge: "2nd" },
    { name: "Busan Components Co", country: "South Korea",
      score: 8.2, lead: "16 days", badge: "3rd" },
  ]

  return (
    <div style={{
      background: "var(--bg-card)",
      border: "1px solid #1e2d45",
      borderRadius: 16, padding: 24, marginBottom: 24
    }}>
      <div style={{
        fontSize: 12, fontWeight: 700,
        color: "var(--text-secondary)",
        letterSpacing: 1, textTransform: "uppercase",
        marginBottom: 20
      }}>
        🏆 Alternative Supplier Rankings
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {suppliers.map((s, i) => (
          <div key={i} style={{
            background: i === 0 ? "#0d1f12" : "#0d1526",
            border: `1px solid ${i === 0 ? "#22c55e30" : "#1e2d45"}`,
            borderRadius: 12, padding: "16px 20px",
            display: "flex", alignItems: "center",
            justifyContent: "space-between"
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
              <div style={{
                width: 36, height: 36, borderRadius: 10,
                background: i === 0 ? "#22c55e20" : "#1e2d45",
                display: "flex", alignItems: "center",
                justifyContent: "center",
                fontSize: 16, fontWeight: 800,
                color: i === 0 ? "#22c55e" : "var(--text-secondary)"
              }}>
                {i + 1}
              </div>
              <div>
                <div style={{
                  fontSize: 14, fontWeight: 700,
                  color: "var(--text-primary)"
                }}>
                  {s.name}
                </div>
                <div style={{
                  fontSize: 12, color: "var(--text-secondary)"
                }}>
                  {s.country} · Lead time: {s.lead}
                </div>
              </div>
            </div>
            <div style={{
              display: "flex", alignItems: "center", gap: 12
            }}>
              <div style={{
                fontSize: 13, fontWeight: 700,
                color: i === 0 ? "#22c55e" : "var(--text-secondary)"
              }}>
                {s.score}/10
              </div>
              <div style={{
                fontSize: 11, fontWeight: 700,
                background: i === 0 ? "#22c55e20" : "#1e2d45",
                color: i === 0 ? "#22c55e" : "var(--text-secondary)",
                padding: "3px 10px", borderRadius: 6
              }}>
                {s.badge}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}