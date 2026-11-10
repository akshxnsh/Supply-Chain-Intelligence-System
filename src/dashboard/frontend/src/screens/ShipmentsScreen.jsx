import { useState, useEffect } from "react"
import axios from "axios"
import { API } from "../config"

const usd = n => (n == null ? "-" : "$" + Math.round(n).toLocaleString("en-US"))
const card = { background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 12 }

// whole days from today (local date) to an ISO date like 2026-11-15
function daysUntil(iso) {
  const [y, m, d] = iso.split("-").map(Number)
  const today = new Date(); today.setHours(0, 0, 0, 0)
  return Math.round((new Date(y, m - 1, d) - today) / 86400000)
}

// Stock cover colour: under 2 weeks is where a delay starts to hurt.
function coverColor(days) {
  if (days == null) return "var(--text-muted)"
  if (days < 14) return "var(--accent-red)"
  if (days < 30) return "var(--accent-yellow)"
  return "var(--accent-green)"
}

function StockCard({ s }) {
  const days = s.days_of_stock
  const pct = Math.min(100, ((days || 0) / 60) * 100)
  const color = coverColor(days)
  return (
    <div style={{ ...card, padding: "16px 18px", borderLeft: `3px solid ${color}` }}>
      <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text-primary)", fontFamily: "monospace" }}>{s.product_category}</div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 6, marginTop: 8 }}>
        <span style={{ fontSize: 30, fontWeight: 800, color }}>{days == null ? "—" : days}</span>
        <span style={{ fontSize: 12, color: "var(--text-muted)" }}>days of stock</span>
      </div>
      <div style={{ height: 6, borderRadius: 3, background: "var(--bg-card-hover)", margin: "8px 0 10px" }} title="Bar = days of stock, full bar = 60 days">
        <div style={{ width: `${pct}%`, height: "100%", borderRadius: 3, background: color }} />
      </div>
      <div style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.6 }}>
        In stock {usd(s.inventory_value_usd)}<br />
        Pending orders {usd(s.pending_orders_value_usd)}<br />
        Demand about {usd(s.daily_demand_usd)} a day
      </div>
    </div>
  )
}

export default function ShipmentsScreen({ businessId }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    axios.get(`${API}/api/company`, { params: { business_id: businessId } })
      .then(r => { if (!cancelled) { r.data.error ? setError("Could not load shipments.") : setError(null); setData(r.data) } })
      .catch(() => { if (!cancelled) setError("Could not load shipments. Is the backend running?") })
    return () => { cancelled = true }
  }, [businessId])

  const ships = data?.shipments || []
  const stock = data?.stock || []
  const total = ships.reduce((s, x) => s + (x.shipment_value_usd || 0), 0)

  return (
    <div style={{ padding: "20px 24px", display: "flex", flexDirection: "column", gap: 16, maxWidth: 1000 }}>
      <div>
        <div style={{ fontSize: 20, fontWeight: 700, color: "var(--text-primary)" }}>Shipments &amp; Stock</div>
        <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 2 }}>
          What is on its way and how long the stock on the shelf lasts. The same numbers the alerts use to decide whether a delay would cause a stockout.
        </div>
      </div>

      {error && <div style={{ ...card, padding: 14, color: "var(--accent-orange)", fontSize: 13 }}>{error}</div>}
      {!error && data === null && <div style={{ color: "var(--text-secondary)", fontSize: 13 }}>Loading…</div>}

      {data && !error && stock.length === 0 && ships.length === 0 && (
        <div style={{ ...card, padding: 18, color: "var(--text-secondary)", fontSize: 14 }}>
          No inventory or shipments are loaded for this business.
        </div>
      )}

      {stock.length > 0 && (
        <>
          <div style={{ fontSize: 14, fontWeight: 700, color: "var(--text-primary)" }}>Stock cover</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))", gap: 12 }}>
            {stock.map(s => <StockCard key={s.product_category} s={s} />)}
          </div>
        </>
      )}

      {ships.length > 0 && (
        <>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: 8, marginTop: 4 }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: "var(--text-primary)" }}>On the way ({ships.length})</div>
            <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>{usd(total)} in transit · soonest arrival first</div>
          </div>
          <div style={{ ...card, overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13, minWidth: 640 }}>
              <thead>
                <tr style={{ color: "var(--text-muted)", textAlign: "left", fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 }}>
                  {["Arrives", "Supplier", "Product", "Value", "Route"].map(h => <th key={h} style={{ padding: "10px 14px", fontWeight: 600 }}>{h}</th>)}
                </tr>
              </thead>
              <tbody>
                {ships.map(x => {
                  const d = daysUntil(x.arrives)
                  return (
                    <tr key={x.shipment_id} style={{ borderTop: "1px solid var(--border)", color: "var(--text-secondary)" }}>
                      <td style={{ padding: "10px 14px", whiteSpace: "nowrap" }}>
                        <b style={{ color: "var(--text-primary)" }}>{x.arrives}</b><br />
                        <span style={{ fontSize: 11, color: d < 0 ? "var(--accent-red)" : "var(--text-muted)" }}>
                          {d < 0 ? `${-d} d overdue` : d === 0 ? "today" : `in ${d} d`}
                        </span>
                      </td>
                      <td style={{ padding: "10px 14px" }}>{x.supplier_name}<br /><span style={{ fontSize: 11, color: "var(--text-muted)" }}>{x.supplier_country}</span></td>
                      <td style={{ padding: "10px 14px", fontFamily: "monospace", fontSize: 12 }}>{x.product_category}</td>
                      <td style={{ padding: "10px 14px", color: "var(--text-primary)", whiteSpace: "nowrap" }}>{usd(x.shipment_value_usd)}</td>
                      <td style={{ padding: "10px 14px", fontSize: 12 }} title={x.route}>{x.origin_port} → {x.destination_port}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}
