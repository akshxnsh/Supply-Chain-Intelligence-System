import { useState, useEffect } from "react"
import axios from "axios"
import Sidebar from "./components/Sidebar"
import AlertsScreen from "./screens/AlertsScreen"
import TraceScreen from "./screens/TraceScreen"
import SupplierHealthScreen from "./screens/SupplierHealthScreen"
import OverviewScreen from "./screens/OverviewScreen"

const API = "http://localhost:8000"
const DEFAULT_BIZ = "demo-business-001"

const SCREEN_TITLES = {
  overview: "Overview",
  alerts: "Active Alerts",
  trace: "Agent Simulation",
  health: "Supplier Health",
}

export default function App() {
  const [screen, setScreen]       = useState("trace")
  const [businesses, setBusinesses] = useState([])
  const [businessId, setBusinessId] = useState(DEFAULT_BIZ)
  const [loading, setLoading]     = useState(false)
  const [result, setResult]       = useState(null)
  const [error, setError]         = useState(null)

  useEffect(() => {
    axios.get(`${API}/api/businesses`)
      .then(res => setBusinesses(res.data.businesses || []))
      .catch(() => {
        setBusinesses([{ id: DEFAULT_BIZ, name: "Mid-Atlantic Auto Parts Distribution LLC", industry: "Automotive Parts Distribution" }])
      })
  }, [])

  async function simulate() {
    if (loading) return
    setLoading(true)
    setResult(null)
    setError(null)
    setScreen("trace")
    try {
      const res = await axios.post(`${API}/api/simulate?business_id=${businessId}`)
      if (res.data.success === false) setError(res.data.error || "Agent failed")
      else setResult(res.data)
    } catch (e) {
      setError("Backend not running")
    } finally {
      setLoading(false)
    }
  }

  function handleSelectBusiness(id) {
    setBusinessId(id)
    setResult(null)
    setError(null)
  }

  return (
    <div style={{ display: "flex", minHeight: "100vh", background: "#000" }}>
      <Sidebar active={screen} onNavigate={setScreen} />

      <div style={{ marginLeft: "var(--sidebar-width)", flex: 1, display: "flex", flexDirection: "column" }}>

        <header style={{
          borderBottom: "1px solid var(--border)",
          padding: "0 32px",
          height: 56,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          background: "#050505",
        }}>
          <span style={{ fontWeight: 700, color: "var(--text-primary)", fontSize: 15 }}>
            {SCREEN_TITLES[screen]}
          </span>

          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <select
              value={businessId}
              onChange={e => handleSelectBusiness(e.target.value)}
              style={{
                background: "var(--bg-card)",
                border: "1px solid var(--border)",
                borderRadius: 8,
                color: "var(--text-primary)",
                padding: "6px 12px",
                fontSize: 13,
                cursor: "pointer",
                outline: "none",
              }}
            >
              {businesses.map(b => (
                <option key={b.id} value={b.id}>{b.name}</option>
              ))}
            </select>

            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <div style={{
                width: 8,
                height: 8,
                borderRadius: "50%",
                background: "var(--accent-green)",
                boxShadow: "0 0 6px var(--accent-green)",
              }} />
              <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>Online</span>
            </div>
          </div>
        </header>

        <main style={{ flex: 1, overflowY: "auto" }}>
          {screen === "overview" && <OverviewScreen />}
          {screen === "alerts" && <AlertsScreen businessId={businessId} />}
          {screen === "trace"  && (
            <TraceScreen
              businessId={businessId}
              loading={loading}
              onSimulate={simulate}
              result={result}
              error={error}
            />
          )}
          {screen === "health" && <SupplierHealthScreen businessId={businessId} />}
        </main>

      </div>
    </div>
  )
}
