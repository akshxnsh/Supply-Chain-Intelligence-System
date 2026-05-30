import { useState } from "react"
import Header from "./components/Header"
import SimulateButton from "./components/SimulateButton"
import DisruptionAlert from "./components/DisruptionAlert"
import ExposureCard from "./components/ExposureCard"
import SupplierScores from "./components/SupplierScores"
import ActionPanel from "./components/ActionPanel"
import axios from "axios"

const API = "http://localhost:8000"

export default function App() {
  const [loading, setLoading]   = useState(false)
  const [result, setResult]     = useState(null)
  const [approved, setApproved] = useState(false)
  const [error, setError]       = useState(null)

  async function simulate() {
    if (loading) return  // Hard block double clicks
    setLoading(true)
    setResult(null)
    setApproved(false)
    setError(null)
    try {
      const res = await axios.post(`${API}/api/simulate`)
      if (res.data.success === false) {
        setError(res.data.error || "Agent failed")
      } else {
        setResult(res.data)
      }
    } catch (e) {
      setError("Agent failed to run. Is the backend running?")
    } finally {
      setLoading(false)
    }
  }

  function approve() {
    setApproved(true)
  }

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg-primary)" }}>
      <Header />

      <main style={{ maxWidth: 1200, margin: "0 auto", padding: "32px 24px" }}>

        {/* Simulate Button — always visible */}
        <SimulateButton
          loading={loading}
          onClick={simulate}
        />

        {/* Error */}
        {error && (
          <div style={{
            background: "#1a0a0a", border: "1px solid var(--accent-red)",
            borderRadius: 12, padding: 16, marginTop: 24, color: "#fca5a5"
          }}>
            ❌ {error}
          </div>
        )}

        {/* Results */}
        {result && result.success && (
          <div style={{ marginTop: 32 }}>

            {/* Top row — disruption + exposure */}
            <div style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: 24, marginBottom: 24
            }}>
              <DisruptionAlert disruption={result.disruption}
                               severity={result.severity_score} />
              <ExposureCard    exposure={result.exposure}
                               supplier={result.top_supplier} />
            </div>

            {/* Supplier scores */}
            <SupplierScores result={result} />

            {/* Action panel — PO + email + approve */}
            <ActionPanel
              result={result}
              approved={approved}
              onApprove={approve}
            />

          </div>
        )}

      </main>
    </div>
  )
}