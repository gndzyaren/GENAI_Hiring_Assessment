import React, { useState, useEffect } from "react"
import mock from "../mockData.json"

// ---------------- TIMER ----------------
function useTimer(seconds: number, onEnd?: () => void) {
  const [time, setTime] = useState(seconds)

  useEffect(() => {
    if (time <= 0) {
      onEnd && onEnd()
      return
    }
    const interval = setInterval(() => setTime((t) => t - 1), 1000)
    return () => clearInterval(interval)
  }, [time])

  const format = () => {
    const m = Math.floor(time / 60)
    const s = time % 60
    return `${m}:${s < 10 ? "0" : ""}${s}`
  }

  return { time, format }
}

// ---------------- HELPERS ----------------
const QUESTIONS_PER_PAGE = 5

function paginate(arr: string[], page: number) {
  const start = page * QUESTIONS_PER_PAGE
  return arr.slice(start, start + QUESTIONS_PER_PAGE)
}

function pickRandom(arr: string[], count: number) {
  return [...arr].sort(() => 0.5 - Math.random()).slice(0, count)
}

function pickOne(arr: string[]) {
  return arr[Math.floor(Math.random() * arr.length)]
}

function detectDomain(jd: string) {
  const t = jd.toLowerCase()
  if (t.includes("power")) return "power_electronics"
  if (t.includes("electrical")) return "electrical"
  return "software"
}

function getLevel(jd: string) {
  const t = jd.toLowerCase()
  if (t.includes("senior") || jd.includes("5")) return "hard"
  if (t.includes("mid") || jd.includes("3")) return "medium"
  return "easy"
}

// ---------------- SCORING ----------------
function checkAnswer(a: string, keys: string[]) {
  if (!a) return 0
  let count = 0
  keys.forEach((k) => {
    if (a.toLowerCase().includes(k.toLowerCase())) count++
  })
  return count / keys.length
}

function calcScore(ans: string[], keys: string[][]) {
  if (!ans.length) return 0
  let total = 0
  ans.forEach((a, i) => (total += checkAnswer(a, keys[i] || [])))
  return Math.round((total / ans.length) * 100)
}

function getRec(score: number) {
  if (score >= 80) return "✅ Strong Hire"
  if (score >= 60) return "👍 Hire"
  return "❌ Not Hire"
}

// ---------------- APP ----------------
export default function App() {
  const [mode, setMode] = useState("recruiter")
  const [page, setPage] = useState("jd")

  const [jd, setJd] = useState("")
  const [includeCoding, setIncludeCoding] = useState(true)

  const [questions, setQuestions] = useState<any>(null)
  const [section, setSection] = useState("behavioral")

  const [pageIndex, setPageIndex] = useState(0)

  const [behavioralAnswers, setBA] = useState<string[]>([])
  const [technicalAnswers, setTA] = useState<string[]>([])

  const [flagB, setFlagB] = useState<number[]>([])
  const [flagT, setFlagT] = useState<number[]>([])

  const [code, setCode] = useState("")
  const [lint, setLint] = useState("")
  const [pyodide, setPyodide] = useState<any>(null)

  // LOAD PYTHON
  useEffect(() => {
    async function load() {
      const p = await (window as any).loadPyodide()
      setPyodide(p)
    }
    load()
  }, [])

  async function fakeLint(input: string) {
    if (!pyodide) return
    const res = await pyodide.runPythonAsync(`
import ast
code = """${input.replace(/"/g, '\\"')}"""
try:
    ast.parse(code)
    "✅ Syntax OK"
except Exception as e:
    "❌ " + str(e)
`)
    setLint(res)
  }

  useEffect(() => {
    const t = setTimeout(() => fakeLint(code), 600)
    return () => clearTimeout(t)
  }, [code])

  useEffect(() => setPageIndex(0), [section])

  // TIMERS
  const behavioralTimer = useTimer(40 * 60, () => setSection("technical"))
  const technicalTimer = useTimer(60 * 60, () =>
    setSection(includeCoding ? "coding" : "submit")
  )
  const codingTimer = useTimer(60 * 60, () => setSection("submit"))

  const timer =
    section === "behavioral"
      ? behavioralTimer
      : section === "technical"
      ? technicalTimer
      : codingTimer

  // GENERATE
  function generate() {
    const domain = detectDomain(jd)
    const level = getLevel(jd)

    setQuestions({
      behavioral: pickRandom(mock.behavioral, 30),
      technical: pickRandom(mock.technical[domain], 30),
      coding: includeCoding
        ? { question: pickOne(mock.coding[level]), difficulty: level }
        : null
    })

    setMode("candidate")
    setPage("assessment")
  }

  // FLAGS
  function toggleFlag(i: number, type: "b" | "t") {
    if (type === "b") {
      setFlagB((p) => (p.includes(i) ? p.filter((x) => x !== i) : [...p, i]))
    } else {
      setFlagT((p) => (p.includes(i) ? p.filter((x) => x !== i) : [...p, i]))
    }
  }

  // PROGRESS
  function Progress({ answers, total }: any) {
    const done = answers.filter((a: string) => a?.length > 5).length
    const percent = (done / total) * 100
    return (
      <div>
        <div style={{ height: 6, background: "#334155" }}>
          <div style={{ width: `${percent}%`, height: "100%", background: "#22c55e" }} />
        </div>
        <p>{Math.round(percent)}%</p>
      </div>
    )
  }

  // SCORES
  const bScore = calcScore(behavioralAnswers, mock.answers?.behavioral || [])
  const tScore = calcScore(technicalAnswers, mock.answers?.technical || [])

  const cScore = includeCoding ? 85 : 0
  const final = includeCoding ? (bScore + tScore + cScore) / 3 : (bScore + tScore) / 2

  // ---------------- UI ----------------
  return (
    <div style={{ display: "flex", height: "100vh", background: "#0f172a", color: "white" }}>

      {/* SIDEBAR */}
      <div style={{ width: 220, background: "#111827", padding: 15 }}>
        <h2>⚡ Engine</h2>
        <button onClick={() => setMode("recruiter")}>Recruiter</button>
        <button onClick={() => setMode("candidate")}>Candidate</button>
        <div onClick={() => setPage("jd")}>JD</div>
        <div onClick={() => setPage("assessment")}>Exam</div>
        <div onClick={() => setPage("eval")}>Eval</div>
      </div>

      {/* MAIN */}
      <div style={{ flex: 1, padding: 20, overflow: "auto" }}>

        {/* JD */}
        {page === "jd" && mode === "recruiter" && (
          <div>
            <h1>JD</h1>
            <textarea value={jd} onChange={(e) => setJd(e.target.value)} />
            <label>
              <input
                type="checkbox"
                checked={includeCoding}
                onChange={() => setIncludeCoding(!includeCoding)}
              />
              Coding
            </label>
            <button onClick={generate}>Generate</button>
          </div>
        )}

        {/* EXAM */}
        {page === "assessment" && questions && mode === "candidate" && (
          <div>

            {/* TIMER */}
            <div style={{ position: "fixed", top: 10, right: 10 }}>
              ⏱ {timer.format()}
            </div>

            {/* BEHAVIORAL */}
            {section === "behavioral" && (
              <div>
                <h2>Behavioral</h2>

                <Progress answers={behavioralAnswers} total={questions.behavioral.length} />

                {paginate(questions.behavioral, pageIndex).map((q: string, i: number) => {
                  const idx = i + pageIndex * QUESTIONS_PER_PAGE
                  return (
                    <div key={idx} style={{
                      border: flagB.includes(idx) ? "2px solid orange" : "1px solid gray",
                      margin: 10, padding: 10
                    }}>
                      <p>{q}</p>
                      <textarea
                        value={behavioralAnswers[idx] || ""}
                        onChange={(e) => {
                          const a = [...behavioralAnswers]
                          a[idx] = e.target.value
                          setBA(a)
                        }}
                      />
                      <button onClick={() => toggleFlag(idx, "b")}>🚩</button>
                    </div>
                  )
                })}

                <button disabled={pageIndex === 0} onClick={() => setPageIndex(pageIndex - 1)}>Prev</button>
                <button onClick={() => setPageIndex(pageIndex + 1)}>Next</button>

                <button onClick={() => setSection("technical")}>Next Section</button>
              </div>
            )}

            {/* TECHNICAL */}
            {section === "technical" && (
              <div>
                <h2>Technical</h2>

                <Progress answers={technicalAnswers} total={questions.technical.length} />

                {paginate(questions.technical, pageIndex).map((q: string, i: number) => {
                  const idx = i + pageIndex * QUESTIONS_PER_PAGE
                  return (
                    <div key={idx} style={{
                      border: flagT.includes(idx) ? "2px solid orange" : "1px solid gray",
                      margin: 10, padding: 10
                    }}>
                      <p>{q}</p>
                      <textarea
                        value={technicalAnswers[idx] || ""}
                        onChange={(e) => {
                          const a = [...technicalAnswers]
                          a[idx] = e.target.value
                          setTA(a)
                        }}
                      />
                      <button onClick={() => toggleFlag(idx, "t")}>🚩</button>
                    </div>
                  )
                })}

                <button disabled={pageIndex === 0} onClick={() => setPageIndex(pageIndex - 1)}>Prev</button>
                <button onClick={() => setPageIndex(pageIndex + 1)}>Next</button>

                <button onClick={() => setSection(includeCoding ? "coding" : "submit")}>
                  Next Section
                </button>
              </div>
            )}

            {/* CODING */}
            {section === "coding" && questions.coding && (
              <div>
                <h2>Coding ({questions.coding.difficulty})</h2>
                <p>{questions.coding.question}</p>

                <textarea value={code} onChange={(e) => setCode(e.target.value)} />
                <p>{lint}</p>

                <button onClick={() => setSection("submit")}>Submit</button>
              </div>
            )}

            {/* SUBMIT */}
            {section === "submit" && (
              <div>
                <h1>✅ Submitted</h1>
                <button onClick={() => setPage("eval")}>View Evaluation</button>
              </div>
            )}
          </div>
        )}

        {/* EVAL */}
        {page === "eval" && (
          <div>
            <h1>Evaluation</h1>
            <p>Behavioral: {bScore}</p>
            <p>Technical: {tScore}</p>
            {includeCoding && <p>Coding: {cScore}</p>}
            <h2>Total: {Math.round(final)}</h2>
            <h1>{getRec(final)}</h1>
          </div>
        )}
      </div>
    </div>
  )
}