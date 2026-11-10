import { useState, useEffect } from "react"
import axios from "axios"
import { API } from "../config"

const card = { background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 12 }
const pct = x => (x == null ? "-" : `${Math.round(x * 1000) / 10}%`)
const color = x => (x == null ? "var(--text-muted)" : x >= 0.9 ? "var(--accent-green)" : x >= 0.7 ? "var(--accent-yellow)" : "var(--accent-orange)")

function Cell({ value, detail }) {
  return (
    <td style={{ padding: "9px 14px", whiteSpace: "nowrap" }}>
      <b style={{ color: color(value) }}>{pct(value)}</b>
      {detail && <span style={{ color: "var(--text-muted)", fontSize: 11, marginLeft: 6 }}>{detail}</span>}
    </td>
  )
}

function ReaderTable({ scores }) {
  const a = scores.all_items, u = scores.unambiguous_items
  const rows = [
    ["Relevant or not (accuracy)", s => s.relevance.accuracy, s => `${s.relevance.tp + s.relevance.tn}/${s.items}`, "Did it decide correctly whether an item matters to a trader?"],
    ["Relevant: precision", s => s.relevance.precision, s => `${s.relevance.tp}/${s.relevance.tp + s.relevance.fp}`, "Of the items it flagged, how many really matter. Low = it over-flags."],
    ["Relevant: recall", s => s.relevance.recall, s => `${s.relevance.tp}/${s.relevance.tp + s.relevance.fn}`, "Of the items that matter, how many it caught."],
    ["Event type", s => s.event_type.accuracy, s => `${s.event_type.correct}/${s.event_type.items}`, "Port strike, tariff, storm and so on."],
    ["Happened / ongoing / expected", s => s.status.accuracy, s => `${s.status.correct}/${s.status.items}`, "Decides between a heads-up and a happening-now alert."],
    ["Expected start date (exact)", s => (s.start_date.gold_with_date ? s.start_date.exact_rate : null), s => `${s.start_date.exact}/${s.start_date.gold_with_date}`, "The date a notice says something starts."],
    ["Country imposing the duty", s => s.imposing_country.accuracy, s => `${s.imposing_country.correct}/${s.imposing_country.items}`, "Decides whether a tariff applies to this trader."],
  ]
  return (
    <div style={{ ...card, overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13, minWidth: 520 }}>
        <thead>
          <tr style={{ textAlign: "left", fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6, color: "var(--text-muted)" }}>
            <th style={{ padding: "10px 14px" }}>What was checked</th>
            <th style={{ padding: "10px 14px" }}>All {a.items} items</th>
            <th style={{ padding: "10px 14px" }} title="Items where reasonable people could not label differently">Clear-cut {u.items} items</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([name, f, d, hint]) => (
            <tr key={name} style={{ borderTop: "1px solid var(--border)", color: "var(--text-secondary)" }}>
              <td style={{ padding: "9px 14px" }} title={hint}>{name}</td>
              <Cell value={f(a)} detail={d(a)} />
              <Cell value={f(u)} detail={d(u)} />
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function QualityScreen() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    axios.get(`${API}/api/quality`).then(r => setData(r.data)).catch(() => setError("Could not load the results. Is the backend running?"))
  }, [])

  const r = data?.reader
  const calls = r && r.cold_run
  return (
    <div style={{ padding: "20px 24px", display: "flex", flexDirection: "column", gap: 14, maxWidth: 980 }}>
      <div>
        <div style={{ fontSize: 20, fontWeight: 700, color: "var(--text-primary)" }}>How well does the AI do?</div>
        <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 2 }}>
          Measured on small labelled samples, with the numbers saved by the evaluation scripts. Nothing here is estimated by the page.
        </div>
      </div>

      {data && !data.labels_reviewed_by_a_person && (
        <div style={{ padding: "10px 14px", borderRadius: 8, fontSize: 13, color: "var(--text-primary)", background: "color-mix(in srgb, var(--accent-yellow) 12%, transparent)", border: "1px solid color-mix(in srgb, var(--accent-yellow) 35%, transparent)" }}>
          <b>Provisional.</b> The "correct answers" these scores are compared against were drafted by an AI assistant and have not been reviewed by a person yet, and the samples are small (one item is about 2 percentage points). Read them as a first measurement, not a final grade.
        </div>
      )}

      {error && <div style={{ ...card, padding: 14, color: "var(--accent-orange)", fontSize: 13 }}>{error}</div>}
      {!error && !data && <div style={{ color: "var(--text-secondary)", fontSize: 13 }}>Loading…</div>}
      {data && !r && <div style={{ ...card, padding: 16, color: "var(--text-secondary)", fontSize: 14 }}>No reader evaluation has been saved yet. Run <code>python -m src.evaluation.reader_eval</code>.</div>}

      {r && (
        <>
          <div style={{ fontSize: 14, fontWeight: 700, color: "var(--text-primary)" }}>The reader <span style={{ fontWeight: 400, color: "var(--text-muted)", fontSize: 12 }}>· turns news and notices into structured facts · model {r.model} · {r.items} real items</span></div>
          <ReaderTable scores={r.scores} />
          <div style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.6 }}>
            Weak spots to know about: it flags too many items as relevant (precision), and it often calls preliminary trade rulings "expected" where the labels say "happened".
            Its dates, event types and countries are right on the clear-cut items.
          </div>

          {calls && (
            <div style={{ ...card, padding: "14px 18px", display: "flex", gap: 28, flexWrap: "wrap" }}>
              <div>
                <div style={{ fontSize: 11, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: 0.6 }}>Model calls, first run</div>
                <div style={{ fontSize: 22, fontWeight: 800, color: "var(--text-primary)" }}>{calls.llm_calls} <span style={{ fontSize: 12, fontWeight: 400, color: "var(--text-muted)" }}>instead of {calls.naive_calls}</span></div>
                <div style={{ fontSize: 12, color: "var(--accent-green)" }}>{calls.call_reduction_pct}% fewer (items sent in batches)</div>
              </div>
              <div>
                <div style={{ fontSize: 11, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: 0.6 }}>Model calls, repeat run</div>
                <div style={{ fontSize: 22, fontWeight: 800, color: "var(--text-primary)" }}>{r.warm_run.llm_calls} <span style={{ fontSize: 12, fontWeight: 400, color: "var(--text-muted)" }}>{r.warm_run.cache_hits}/{r.warm_run.items} from cache</span></div>
                <div style={{ fontSize: 12, color: "var(--accent-green)" }}>nothing is read twice</div>
              </div>
            </div>
          )}
        </>
      )}

      {data?.judge?.length > 0 && (
        <>
          <div style={{ fontSize: 14, fontWeight: 700, color: "var(--text-primary)", marginTop: 6 }}>
            The judge's explanations <span style={{ fontWeight: 400, color: "var(--text-muted)", fontSize: 12 }}>· is each explanation supported by the evidence it cites?</span>
          </div>
          <div style={{ ...card, overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13, minWidth: 520 }}>
              <thead>
                <tr style={{ textAlign: "left", fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6, color: "var(--text-muted)" }}>
                  {["Answers written by", "Answers", "Agrees: supported or not", "Agrees exactly", "Bad answers caught"].map(h => <th key={h} style={{ padding: "10px 14px" }}>{h}</th>)}
                </tr>
              </thead>
              <tbody>
                {data.judge.map(j => (
                  <tr key={j.judged_model} style={{ borderTop: "1px solid var(--border)", color: "var(--text-secondary)" }}>
                    <td style={{ padding: "9px 14px", fontFamily: "monospace", fontSize: 12 }}>{j.judged_model}</td>
                    <td style={{ padding: "9px 14px" }}>{j.cases}</td>
                    <Cell value={j.agreement_fully_supported_vs_not} />
                    <Cell value={j.exact_agreement} />
                    <td style={{ padding: "9px 14px" }}>{j.llm_flagged_those_as_not_fully_supported}/{j.hand_graded_unsupported}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.6 }}>
            Each answer was graded by {data.grader_model} (a different model from the one that wrote it) and compared with hand grades.
            Besides this AI check, every number, date and cited source in a judge answer is also verified by code before it is shown.
            Samples of 14 to 15 answers are too small to rely on a single AI grader.
          </div>
        </>
      )}
    </div>
  )
}
