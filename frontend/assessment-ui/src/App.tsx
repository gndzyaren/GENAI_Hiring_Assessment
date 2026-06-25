import { useState, useEffect, useRef } from "react"

const API = "http://localhost:8000"

// ---- Types ----------------------------------------------------------------

interface Question {
  question_id: string
  section: string
  difficulty: number
  question_text: string
  options: string[] | null
  question_number: number
}

interface AnswerResp {
  is_correct: boolean
  score: number
  feedback: string
  next_question: Question | null
  section_complete: boolean
  exam_complete: boolean
}

interface Results {
  session_id: string
  candidate_name: string | null
  total_questions: number
  total_score: number
  section_scores: Record<string, number>
  status: string
}

interface JobListing {
  job_id: string
  title: string
  include_coding: boolean
  created_at: string
}

interface RecruiterJob {
  job_id: string
  title: string
  status: string
  bank_status: string
  include_coding: boolean
  candidate_count: number
  created_at: string
}

interface Candidate {
  candidate_id: string
  name: string
  email: string
  session_id: string | null
  total_score: number | null
  status: string
  applied_at: string
  feedback_summary?: { strong_areas: string[]; weak_areas: string[] } | null
}

interface ResponseItem {
  question_number: number
  section: string
  difficulty: number
  question_text: string
  options: string[] | null
  candidate_answer: string | null
  correct_answer: string
  is_correct: boolean | null
  score: number | null
  feedback: string | null
}

// ---- Timer ----------------------------------------------------------------

function useTimer(initialSeconds: number) {
  const [time, setTime] = useState(initialSeconds)
  const ref = useRef<ReturnType<typeof setInterval>>()

  useEffect(() => {
    ref.current = setInterval(() => setTime((t: number) => Math.max(t - 1, 0)), 1000)
    return () => clearInterval(ref.current)
  }, [])

  function reset(s: number) { setTime(s) }

  function format() {
    const m = Math.floor(time / 60)
    const s = time % 60
    return `${m}:${s < 10 ? "0" : ""}${s}`
  }

  return { time, format, reset }
}

// ---- Styles ---------------------------------------------------------------

const c = {
  bg: "#0f172a",
  surface: "#1e293b",
  border: "#334155",
  muted: "#64748b",
  text: "#e2e8f0",
  subtext: "#94a3b8",
  accent: "#6366f1",
  accentHover: "#4f46e5",
  green: "#22c55e",
  red: "#f87171",
  yellow: "#eab308",
}

const st = {
  page: { display: "flex" as const, minHeight: "100vh", background: c.bg, color: c.text, fontFamily: "system-ui, -apple-system, sans-serif" },
  sidebar: { width: 210, minHeight: "100vh", background: c.surface, padding: "28px 16px", display: "flex" as const, flexDirection: "column" as const, gap: 4, borderRight: `1px solid ${c.border}` },
  main: { flex: 1, padding: "48px 48px", overflowY: "auto" as const },
  card: { background: c.surface, borderRadius: 12, padding: 28, marginBottom: 20, border: `1px solid ${c.border}` },
  input: { width: "100%", background: c.bg, border: `1px solid ${c.border}`, borderRadius: 8, padding: "10px 14px", color: c.text, fontSize: 14, marginBottom: 12, boxSizing: "border-box" as const, outline: "none" },
  label: { display: "block" as const, fontSize: 12, color: c.subtext, marginBottom: 6, fontWeight: 500, letterSpacing: "0.05em", textTransform: "uppercase" as const },
  btn: { background: c.accent, color: "white", border: "none", borderRadius: 8, padding: "10px 22px", cursor: "pointer", fontSize: 14, fontWeight: 600 },
  btnGhost: { background: "transparent", color: c.subtext, border: `1px solid ${c.border}`, borderRadius: 8, padding: "8px 14px", cursor: "pointer", fontSize: 13, width: "100%", textAlign: "left" as const, marginBottom: 2 },
  option: (selected: boolean) => ({
    display: "block", width: "100%", textAlign: "left" as const,
    background: selected ? "#312e81" : c.bg,
    border: `2px solid ${selected ? c.accent : c.border}`,
    borderRadius: 8, padding: "12px 16px", color: c.text,
    cursor: "pointer", fontSize: 14, marginBottom: 8,
  }),
}

// ---- App ------------------------------------------------------------------

type Page = "home" | "recruiter-setup" | "recruiter-dashboard" | "candidate-join" | "exam" | "complete"

export default function App() {
  const [page, setPage] = useState<Page>("home")
  const [err, setErr] = useState("")
  const [loading, setLoading] = useState(false)

  // Recruiter
  const [jobTitle, setJobTitle] = useState("")
  const [jobDesc, setJobDesc] = useState("")
  const [recruiterEmail, setRecruiterEmail] = useState("")
  const [jobId, setJobId] = useState("")
  const [includeCoding, setIncludeCoding] = useState(true)
  const [bankStatus, setBankStatus] = useState<"generating" | "ready" | "error" | "">("")
  const [recruiterJobs, setRecruiterJobs] = useState<RecruiterJob[]>([])
  const [recruiterJobsLoading, setRecruiterJobsLoading] = useState(false)
  const [candidates, setCandidates] = useState<Candidate[]>([])
  const bankPollRef = useRef<ReturnType<typeof setInterval> | undefined>(undefined)
  const [transcripts, setTranscripts] = useState<Record<string, ResponseItem[]>>({})
  const [expandedCandidate, setExpandedCandidate] = useState<string | null>(null)
  const [transcriptLoading, setTranscriptLoading] = useState<string | null>(null)

  // Candidate
  const [jobListings, setJobListings] = useState<JobListing[]>([])
  const [jobListingsLoading, setJobListingsLoading] = useState(false)
  const [selectedJob, setSelectedJob] = useState<JobListing | null>(null)
  const [joinJobId, setJoinJobId] = useState("")
  const [name, setName] = useState("")
  const [email, setEmail] = useState("")
  const [sessionId, setSessionId] = useState("")
  const [question, setQuestion] = useState<Question | null>(null)
  const [selected, setSelected] = useState("")
  const [feedback, setFeedback] = useState<{ text: string; correct: boolean } | null>(null)
  const [results, setResults] = useState<Results | null>(null)

  // Pyodide (coding syntax check)
  const [pyodide, setPyodide] = useState<any>(null)
  const [lint, setLint] = useState("")

  // Timer — 40 min screening, 60 min coding
  const timer = useTimer(40 * 60)
  const prevSection = useRef("")
  useEffect(() => {
    if (!question) return
    if (question.section !== prevSection.current) {
      prevSection.current = question.section
      timer.reset(question.section === "coding" ? 60 * 60 : 40 * 60)
    }
  }, [question?.section])

  // Load Pyodide once
  useEffect(() => {
    ;(async () => {
      try {
        const p = await (window as any).loadPyodide()
        setPyodide(p)
      } catch { /* Pyodide unavailable — coding lint just won't show */ }
    })()
  }, [])

  // Fetch job listings when candidate page is opened
  useEffect(() => {
    if (page === "candidate-join" && !selectedJob) fetchJobListings()
    if (page === "recruiter-setup") fetchRecruiterJobs()
  }, [page])

  // Lint on code change (debounced)
  useEffect(() => {
    if (!selected || question?.options) return
    const t = setTimeout(async () => {
      if (!pyodide) return
      const res = await pyodide.runPythonAsync(`
import ast
code = """${selected.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"""
try:
    ast.parse(code)
    "✅ Syntax OK"
except Exception as e:
    "❌ " + str(e)
`)
      setLint(res)
    }, 600)
    return () => clearTimeout(t)
  }, [selected])

  // ---- API helpers --------------------------------------------------------

  async function api<T>(path: string, opts?: RequestInit): Promise<T> {
    const res = await fetch(`${API}${path}`, { headers: { "Content-Type": "application/json" }, ...opts })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail ?? "Request failed")
    return data as T
  }

  async function fetchRecruiterJobs() {
    setRecruiterJobsLoading(true)
    try {
      const data = await api<RecruiterJob[]>("/recruiter/jobs")
      setRecruiterJobs(data)
    } catch { /* ignore */ }
    finally { setRecruiterJobsLoading(false) }
  }

  function startBankPoll(id: string) {
    clearInterval(bankPollRef.current)
    setBankStatus("generating")
    bankPollRef.current = setInterval(async () => {
      try {
        const job = await api<{ bank_status: string }>(`/jobs/${id}`)
        if (job.bank_status === "ready" || job.bank_status === "error") {
          clearInterval(bankPollRef.current)
          setBankStatus(job.bank_status as "ready" | "error")
        }
      } catch { /* ignore transient fetch errors */ }
    }, 3000)
  }

  async function createJob() {
    setLoading(true); setErr("")
    try {
      const data = await api<{ job_id: string; bank_status: string }>("/jobs", {
        method: "POST",
        body: JSON.stringify({ title: jobTitle, job_description: jobDesc, recruiter_email: recruiterEmail, include_coding: includeCoding }),
      })
      setJobId(data.job_id)
      setBankStatus(data.bank_status as "generating" | "ready" | "error")
      setPage("recruiter-dashboard")
      if (data.bank_status !== "ready") startBankPoll(data.job_id)
    } catch (e: any) { setErr(e.message) }
    finally { setLoading(false) }
  }

  async function refreshResults() {
    setLoading(true); setErr("")
    try {
      const data = await api<{ candidates: Candidate[] }>(`/jobs/${jobId}/results`)
      setCandidates(data.candidates)
    } catch (e: any) { setErr(e.message) }
    finally { setLoading(false) }
  }

  async function toggleTranscript(candidateId: string, sessionId: string) {
    if (expandedCandidate === candidateId) {
      setExpandedCandidate(null)
      return
    }
    setExpandedCandidate(candidateId)
    if (transcripts[sessionId]) return
    setTranscriptLoading(candidateId)
    try {
      const data = await api<{ responses: ResponseItem[] }>(`/exam/${sessionId}/transcript`)
      setTranscripts(prev => ({ ...prev, [sessionId]: data.responses }))
    } catch { /* ignore */ }
    finally { setTranscriptLoading(null) }
  }

  async function downloadResults() {
    const completed = candidates.filter(c => c.status === "completed" && c.session_id)
    const rows = await Promise.all(
      completed.map(async c => {
        try {
          const t = await api<{ responses: ResponseItem[] }>(`/exam/${c.session_id}/transcript`)
          return { ...c, responses: t.responses }
        } catch {
          return { ...c, responses: [] }
        }
      })
    )
    const blob = new Blob(
      [JSON.stringify({ job_id: jobId, exported_at: new Date().toISOString(), candidates: rows }, null, 2)],
      { type: "application/json" }
    )
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `results-${jobId.slice(0, 8)}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  async function fetchJobListings() {
    setJobListingsLoading(true)
    try {
      const data = await api<JobListing[]>("/jobs")
      setJobListings(data)
    } catch { /* ignore */ }
    finally { setJobListingsLoading(false) }
  }

  async function startExam() {
    setLoading(true); setErr("")
    try {
      const data = await api<{ session_id: string; question: Question }>(`/jobs/${joinJobId}/apply`, {
        method: "POST",
        body: JSON.stringify({ name, email }),
      })
      setSessionId(data.session_id)
      setQuestion(data.question)
      setPage("exam")
    } catch (e: any) { setErr(e.message) }
    finally { setLoading(false) }
  }

  async function submitAnswer() {
    if (!selected) return
    setLoading(true); setErr("")
    try {
      const data = await api<AnswerResp>(`/exam/${sessionId}/answer`, {
        method: "POST",
        body: JSON.stringify({ answer: selected }),
      })
      setFeedback({ text: data.feedback, correct: data.is_correct })
      setSelected("")
      setLint("")

      if (data.exam_complete) {
        const r = await api<Results>(`/exam/${sessionId}/results`)
        setResults(r)
        setTimeout(() => { setFeedback(null); setPage("complete") }, 1600)
      } else if (data.next_question) {
        setTimeout(() => { setFeedback(null); setQuestion(data.next_question) }, 1800)
      }
    } catch (e: any) { setErr(e.message) }
    finally { setLoading(false) }
  }

  // ---- Helpers ------------------------------------------------------------

  function sectionLabel(s: string) {
    return s === "screening" ? "Screening" : "Coding Assessment"
  }

  function scoreColor(s: number) {
    if (s >= 0.8) return c.green
    if (s >= 0.6) return c.yellow
    return c.red
  }

  function nav(p: Page) { setErr(""); setPage(p) }

  // ---- UI -----------------------------------------------------------------

  return (
    <div style={st.page}>

      {/* Sidebar */}
      <div style={st.sidebar}>
        <div style={{ marginBottom: 28 }}>
          <div style={{ fontSize: 16, fontWeight: 700, color: c.accent }}>⚡ Exam Recruiter</div>
          <div style={{ fontSize: 11, color: c.muted, marginTop: 3 }}>MVP</div>
        </div>
        <button style={st.btnGhost} onClick={() => nav("home")}>🏠 Home</button>
        <button style={st.btnGhost} onClick={() => nav("recruiter-setup")}>👔 Recruiter</button>
        <button style={st.btnGhost} onClick={() => nav("candidate-join")}>🧑‍💻 Candidate</button>
        {jobId && (
          <div style={{ marginTop: 20, padding: "10px 12px", background: c.bg, borderRadius: 8, border: `1px solid ${c.border}` }}>
            <div style={{ fontSize: 10, color: c.muted, marginBottom: 4 }}>ACTIVE JOB</div>
            <div style={{ fontFamily: "monospace", fontSize: 11, color: c.accent, wordBreak: "break-all" }}>{jobId}</div>
          </div>
        )}
      </div>

      {/* Main */}
      <div style={st.main}>

        {/* Home */}
        {page === "home" && (
          <div style={{ maxWidth: 600 }}>
            <h1 style={{ fontSize: 30, fontWeight: 700, marginBottom: 8, marginTop: 0 }}>AI Hiring Assessment</h1>
            <p style={{ color: c.subtext, marginBottom: 40, fontSize: 15 }}>
              Adaptive AI-powered screening. Questions are generated live from the job description.
            </p>
            <div style={{ display: "flex", gap: 16 }}>
              {[
                { icon: "👔", title: "Recruiter", desc: "Post a job and review ranked candidate scores", p: "recruiter-setup" as Page },
                { icon: "🧑‍💻", title: "Candidate", desc: "Take the assessment with your job ID", p: "candidate-join" as Page },
              ].map(item => (
                <div key={item.title} style={{ ...st.card, flex: 1, cursor: "pointer", transition: "border-color 0.15s" }}
                  onClick={() => nav(item.p)}>
                  <div style={{ fontSize: 28, marginBottom: 14 }}>{item.icon}</div>
                  <div style={{ fontWeight: 600, fontSize: 16, marginBottom: 6 }}>{item.title}</div>
                  <div style={{ color: c.subtext, fontSize: 13, lineHeight: 1.5 }}>{item.desc}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Recruiter setup */}
        {page === "recruiter-setup" && (
          <div style={{ maxWidth: 580 }}>
            <h2 style={{ marginTop: 0, marginBottom: 24 }}>Create a Job</h2>
            <div style={st.card}>
              <label style={st.label}>Job Title</label>
              <input style={st.input} value={jobTitle} onChange={e => setJobTitle(e.target.value)} placeholder="e.g. Backend Engineer" />
              <label style={st.label}>Job Description</label>
              <textarea style={{ ...st.input, height: 180, resize: "vertical" }} value={jobDesc}
                onChange={e => setJobDesc(e.target.value)} placeholder="Paste the full job description..." />
              <label style={st.label}>Your Email</label>
              <input style={st.input} value={recruiterEmail} onChange={e => setRecruiterEmail(e.target.value)} placeholder="recruiter@company.com" />
              <div
                onClick={() => setIncludeCoding(v => !v)}
                style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px 14px", background: c.bg, border: `1px solid ${includeCoding ? c.accent : c.border}`, borderRadius: 8, cursor: "pointer", marginBottom: 16, userSelect: "none" }}
              >
                <div style={{ width: 36, height: 20, borderRadius: 10, background: includeCoding ? c.accent : c.border, position: "relative", transition: "background 0.2s", flexShrink: 0 }}>
                  <div style={{ position: "absolute", top: 3, left: includeCoding ? 19 : 3, width: 14, height: 14, borderRadius: "50%", background: "white", transition: "left 0.2s" }} />
                </div>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 600, color: c.text }}>Include coding section</div>
                  <div style={{ fontSize: 12, color: c.muted, marginTop: 2 }}>
                    {includeCoding ? "Candidates will complete 3 coding problems after screening" : "Assessment ends after the 20-question screening section"}
                  </div>
                </div>
              </div>
              {err && <p style={{ color: c.red, fontSize: 13, marginBottom: 12 }}>{err}</p>}
              <button style={st.btn} onClick={createJob} disabled={loading || !jobTitle || !jobDesc || !recruiterEmail}>
                {loading ? "Creating…" : "Create Job →"}
              </button>
            </div>

            <div style={{ ...st.card, marginTop: 8 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
                <div style={{ fontWeight: 600 }}>Existing Jobs</div>
                <button style={{ ...st.btnGhost, width: "auto", padding: "4px 10px", fontSize: 12, marginBottom: 0 }} onClick={fetchRecruiterJobs}>
                  {recruiterJobsLoading ? "Loading…" : "Refresh"}
                </button>
              </div>
              {recruiterJobsLoading && <p style={{ color: c.muted, fontSize: 13, margin: 0 }}>Loading…</p>}
              {!recruiterJobsLoading && recruiterJobs.length === 0 && (
                <p style={{ color: c.muted, fontSize: 13, margin: 0 }}>No jobs yet.</p>
              )}
              {recruiterJobs.map((j, i) => (
                <div
                  key={j.job_id}
                  style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 0", borderBottom: i < recruiterJobs.length - 1 ? `1px solid ${c.border}` : "none", cursor: j.bank_status === "ready" ? "pointer" : "default" }}
                  onClick={() => {
                    if (j.bank_status !== "ready") return
                    setJobId(j.job_id)
                    setBankStatus("ready")
                    refreshResults()
                    nav("recruiter-dashboard")
                  }}
                >
                  <div>
                    <div style={{ fontSize: 14, fontWeight: 500 }}>{j.title}</div>
                    <div style={{ fontSize: 11, color: c.muted, marginTop: 2 }}>
                      {j.candidate_count} candidate{j.candidate_count !== 1 ? "s" : ""} · {j.include_coding ? "Screening + Coding" : "Screening only"}
                    </div>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <span style={{ fontSize: 11, padding: "2px 8px", borderRadius: 4, background: j.status === "closed" ? "#450a0a44" : "#14532d44", color: j.status === "closed" ? "#f87171" : "#4ade80" }}>
                      {j.status}
                    </span>
                    {j.bank_status !== "ready" && (
                      <span style={{ fontSize: 11, color: c.muted }}>{j.bank_status}</span>
                    )}
                    {j.bank_status === "ready" && <span style={{ color: c.accent, fontSize: 14 }}>→</span>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Recruiter dashboard */}
        {page === "recruiter-dashboard" && (
          <div style={{ maxWidth: 680 }}>
            <h2 style={{ marginTop: 0, marginBottom: 6 }}>Job Created ✓</h2>
            <p style={{ color: c.subtext, marginBottom: 24 }}>
              {bankStatus === "ready"
                ? "Share the Job ID with candidates so they can start the assessment."
                : bankStatus === "error"
                ? "Question bank generation failed. Candidates cannot start yet."
                : "Generating question bank in the background — this takes ~60s. You can share the Job ID once it's ready."}
            </p>

            <div style={st.card}>
              {bankStatus === "generating" ? (
                <div style={{ display: "flex", alignItems: "center", gap: 14, padding: "8px 0" }}>
                  <div style={{ width: 20, height: 20, border: `3px solid ${c.accent}`, borderTopColor: "transparent", borderRadius: "50%", animation: "spin 0.9s linear infinite" }} />
                  <span style={{ color: c.subtext, fontSize: 14 }}>Generating question bank (30 questions × 3 difficulty levels)…</span>
                </div>
              ) : bankStatus === "error" ? (
                <p style={{ color: c.red, margin: 0 }}>Bank generation failed. Please recreate the job.</p>
              ) : (
                <>
                  <div style={st.label}>Job ID</div>
                  <div style={{ fontFamily: "monospace", fontSize: 15, color: "#a5b4fc", marginBottom: 16 }}>{jobId}</div>
                  <div style={{ display: "flex", gap: 10 }}>
                    <button style={st.btnGhost} onClick={() => navigator.clipboard.writeText(jobId)}>📋 Copy ID</button>
                    <button style={st.btn} onClick={refreshResults}>{loading ? "Loading…" : "Refresh Results"}</button>
                    {candidates.length > 0 && (
                      <button style={st.btnGhost} onClick={downloadResults}>⬇ Download Results</button>
                    )}
                  </div>
                </>
              )}
            </div>

            <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>

            {candidates.length > 0 && (
              <div style={st.card}>
                <h3 style={{ marginTop: 0, marginBottom: 16 }}>Candidates ({candidates.length})</h3>
                {candidates.map((c2, i) => {
                  const isExpanded = expandedCandidate === c2.candidate_id
                  const isLoadingThis = transcriptLoading === c2.candidate_id
                  const sessionResponses = c2.session_id ? transcripts[c2.session_id] : undefined
                  return (
                    <div key={c2.candidate_id} style={{ borderBottom: i < candidates.length - 1 ? `1px solid ${c.border}` : "none" }}>
                      {/* Candidate header row */}
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "16px 0", paddingBottom: c2.feedback_summary || isExpanded ? 12 : 16 }}>
                        <div>
                          <div style={{ fontWeight: 600 }}>{c2.name}</div>
                          <div style={{ fontSize: 12, color: c.muted }}>{c2.email}</div>
                        </div>
                        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
                          <span style={{ fontSize: 12, color: c.muted, textTransform: "capitalize" }}>{c2.status}</span>
                          <span style={{ fontWeight: 700, fontSize: 20, color: c2.total_score != null ? scoreColor(c2.total_score) : c.muted }}>
                            {c2.total_score != null ? `${Math.round(c2.total_score * 100)}%` : "—"}
                          </span>
                          {c2.session_id && c2.status === "completed" && (
                            <button
                              style={{ ...st.btnGhost, width: "auto", padding: "4px 10px", fontSize: 12, marginBottom: 0 }}
                              onClick={() => toggleTranscript(c2.candidate_id, c2.session_id!)}
                            >
                              {isExpanded ? "Hide ▲" : "Answers ▼"}
                            </button>
                          )}
                        </div>
                      </div>

                      {/* Feedback areas */}
                      {c2.feedback_summary && (
                        <div style={{ display: "flex", gap: 12, marginBottom: 12 }}>
                          <div style={{ flex: 1, background: "#14532d22", border: "1px solid #166534", borderRadius: 8, padding: "10px 14px" }}>
                            <div style={{ fontSize: 11, fontWeight: 700, color: "#4ade80", marginBottom: 6, letterSpacing: "0.05em" }}>STRONG AREAS</div>
                            {c2.feedback_summary.strong_areas?.map((area: string) => (
                              <div key={area} style={{ fontSize: 13, color: c.text, marginBottom: 2 }}>· {area}</div>
                            ))}
                          </div>
                          <div style={{ flex: 1, background: "#450a0a22", border: "1px solid #7f1d1d", borderRadius: 8, padding: "10px 14px" }}>
                            <div style={{ fontSize: 11, fontWeight: 700, color: "#f87171", marginBottom: 6, letterSpacing: "0.05em" }}>WEAK AREAS</div>
                            {c2.feedback_summary.weak_areas?.map((area: string) => (
                              <div key={area} style={{ fontSize: 13, color: c.text, marginBottom: 2 }}>· {area}</div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Q&A transcript */}
                      {isExpanded && (
                        <div style={{ marginBottom: 16 }}>
                          {isLoadingThis ? (
                            <div style={{ color: c.muted, fontSize: 13, padding: "8px 0" }}>Loading answers…</div>
                          ) : sessionResponses && sessionResponses.length > 0 ? (
                            sessionResponses.map((r) => (
                              <div key={r.question_number} style={{ marginBottom: 10, background: c.bg, borderRadius: 8, padding: "12px 14px", border: `1px solid ${r.is_correct ? "#166534" : r.is_correct === false ? "#7f1d1d" : c.border}` }}>
                                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                                  <span style={{ fontSize: 11, color: c.muted, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>
                                    Q{r.question_number} · {r.section} · {"●".repeat(r.difficulty)}{"○".repeat(5 - r.difficulty)}
                                  </span>
                                  {r.score != null && (
                                    <span style={{ fontSize: 12, fontWeight: 700, color: scoreColor(r.score) }}>
                                      {Math.round(r.score * 100)}%
                                    </span>
                                  )}
                                </div>
                                <div style={{ fontSize: 13, color: c.text, marginBottom: 8, lineHeight: 1.5 }}>{r.question_text}</div>
                                {r.options && (
                                  <div style={{ marginBottom: 8 }}>
                                    {r.options.map((opt) => {
                                      const letter = opt[0]
                                      const isChosen = r.candidate_answer?.toUpperCase() === letter.toUpperCase()
                                      const isCorrect = r.correct_answer?.toUpperCase() === letter.toUpperCase()
                                      return (
                                        <div key={opt} style={{
                                          fontSize: 12, padding: "4px 10px", borderRadius: 6, marginBottom: 3,
                                          background: isCorrect ? "#14532d44" : isChosen && !isCorrect ? "#450a0a44" : "transparent",
                                          color: isCorrect ? "#4ade80" : isChosen && !isCorrect ? "#f87171" : c.subtext,
                                          border: `1px solid ${isCorrect ? "#166534" : isChosen && !isCorrect ? "#7f1d1d" : "transparent"}`,
                                        }}>
                                          {opt} {isChosen && !isCorrect ? "← candidate" : ""}{isCorrect && isChosen ? "← ✓" : isCorrect ? "← correct" : ""}
                                        </div>
                                      )
                                    })}
                                  </div>
                                )}
                                {!r.options && r.candidate_answer && (
                                  <div style={{ marginBottom: 6 }}>
                                    <div style={{ fontSize: 11, color: c.muted, marginBottom: 4, fontWeight: 600, textTransform: "uppercase" as const, letterSpacing: "0.05em" }}>Candidate's Answer</div>
                                    <div style={{ fontSize: 12, color: c.subtext, fontFamily: "monospace", whiteSpace: "pre-wrap", background: "#0f172a", padding: "8px 10px", borderRadius: 6 }}>
                                      {r.candidate_answer}
                                    </div>
                                  </div>
                                )}
                                {!r.options && r.correct_answer && (
                                  <div style={{ marginBottom: 6 }}>
                                    <div style={{ fontSize: 11, color: "#4ade80", marginBottom: 4, fontWeight: 600, textTransform: "uppercase" as const, letterSpacing: "0.05em" }}>Model Answer / Criteria</div>
                                    <div style={{ fontSize: 12, color: c.subtext, fontFamily: "monospace", whiteSpace: "pre-wrap", background: "#0f172a", padding: "8px 10px", borderRadius: 6 }}>
                                      {r.correct_answer}
                                    </div>
                                  </div>
                                )}
                                {r.feedback && (
                                  <div style={{ fontSize: 12, color: c.muted, borderTop: `1px solid ${c.border}`, paddingTop: 6, marginTop: 4 }}>{r.feedback}</div>
                                )}
                              </div>
                            ))
                          ) : (
                            <div style={{ color: c.muted, fontSize: 13 }}>No answered questions found.</div>
                          )}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}

            {candidates.length === 0 && (
              <p style={{ color: c.muted, fontSize: 14 }}>No candidates yet. Hit Refresh Results after someone completes the exam.</p>
            )}
            {err && <p style={{ color: c.red, fontSize: 13 }}>{err}</p>}
          </div>
        )}

        {/* Candidate join */}
        {page === "candidate-join" && (
          <div style={{ maxWidth: 560 }}>
            <h2 style={{ marginTop: 0, marginBottom: 6 }}>Open Positions</h2>
            <p style={{ color: c.subtext, marginBottom: 24, fontSize: 14 }}>Select a role to begin your assessment.</p>

            {/* Job listing */}
            {!selectedJob && (
              <div>
                {jobListingsLoading && <p style={{ color: c.muted, fontSize: 14 }}>Loading positions…</p>}
                {!jobListingsLoading && jobListings.length === 0 && (
                  <p style={{ color: c.muted, fontSize: 14 }}>No open positions at the moment.</p>
                )}
                {jobListings.map(j => (
                  <div
                    key={j.job_id}
                    style={{ ...st.card, cursor: "pointer", marginBottom: 12, display: "flex", justifyContent: "space-between", alignItems: "center" }}
                    onClick={() => { setSelectedJob(j); setJoinJobId(j.job_id) }}
                  >
                    <div>
                      <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 4 }}>{j.title}</div>
                      <div style={{ fontSize: 12, color: c.muted }}>
                        {j.include_coding ? "Screening + Coding" : "Screening only"} · Posted {new Date(j.created_at).toLocaleDateString()}
                      </div>
                    </div>
                    <span style={{ color: c.accent, fontSize: 18 }}>→</span>
                  </div>
                ))}
                <button style={{ ...st.btnGhost, width: "auto", marginTop: 8 }} onClick={fetchJobListings}>
                  {jobListingsLoading ? "Loading…" : "Refresh"}
                </button>
              </div>
            )}

            {/* Application form — shown after selecting a job */}
            {selectedJob && (
              <div>
                <button style={{ ...st.btnGhost, width: "auto", marginBottom: 16 }} onClick={() => { setSelectedJob(null); setJoinJobId(""); setErr("") }}>
                  ← Back to positions
                </button>
                <div style={st.card}>
                  <div style={{ marginBottom: 16, paddingBottom: 16, borderBottom: `1px solid ${c.border}` }}>
                    <div style={{ fontSize: 11, color: c.muted, marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.05em" }}>Applying for</div>
                    <div style={{ fontWeight: 600, fontSize: 16 }}>{selectedJob.title}</div>
                    <div style={{ fontSize: 12, color: c.muted, marginTop: 2 }}>
                      {selectedJob.include_coding ? "Screening + Coding assessment" : "Screening assessment only"}
                    </div>
                  </div>
                  <label style={st.label}>Your Name</label>
                  <input style={st.input} value={name} onChange={e => setName(e.target.value)} placeholder="Jane Smith" />
                  <label style={st.label}>Your Email</label>
                  <input style={st.input} value={email} onChange={e => setEmail(e.target.value)} placeholder="jane@example.com" />
                  {err && <p style={{ color: c.red, fontSize: 13, marginBottom: 12 }}>{err}</p>}
                  <button style={st.btn} onClick={startExam} disabled={loading || !name || !email}>
                    {loading ? "Starting…" : "Begin Assessment →"}
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Exam */}
        {page === "exam" && question && (
          <div style={{ maxWidth: 660 }}>
            {/* Header bar */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span style={{ background: c.accent + "33", color: c.accent, borderRadius: 6, padding: "3px 10px", fontSize: 12, fontWeight: 600 }}>
                  {sectionLabel(question.section)}
                </span>
                <span style={{ color: c.muted, fontSize: 13 }}>Question {question.question_number}</span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
                <span style={{ fontSize: 12, color: c.muted }}>
                  {"●".repeat(question.difficulty)}{"○".repeat(5 - question.difficulty)}
                </span>
                <span style={{ fontFamily: "monospace", fontSize: 15, color: timer.time < 300 ? c.red : c.subtext }}>
                  ⏱ {timer.format()}
                </span>
              </div>
            </div>

            <div style={st.card}>
              <p style={{ fontSize: 16, lineHeight: 1.75, marginTop: 0, marginBottom: 24 }}>{question.question_text}</p>

              {/* Multiple choice */}
              {question.options && !feedback && (
                <div>
                  {question.options.map((opt, i) => (
                    <button key={i} style={st.option(selected === opt[0])} onClick={() => setSelected(opt[0])}>
                      {opt}
                    </button>
                  ))}
                </div>
              )}

              {/* Numerical — short text input */}
              {!question.options && !feedback && question.section !== "coding" && (
                <input
                  style={{ ...st.input, marginBottom: 8 }}
                  value={selected}
                  onChange={e => setSelected(e.target.value)}
                  placeholder="Enter your answer…"
                  onKeyDown={e => { if (e.key === "Enter" && selected) submitAnswer() }}
                />
              )}

              {/* Coding — large free-text editor with Pyodide lint */}
              {!question.options && !feedback && question.section === "coding" && (
                <div>
                  <textarea
                    style={{ ...st.input, height: 220, fontFamily: "monospace", fontSize: 13, marginBottom: 8 }}
                    value={selected}
                    onChange={e => setSelected(e.target.value)}
                    placeholder="Write your solution here…"
                  />
                  {lint && (
                    <div style={{ fontSize: 12, color: lint.startsWith("✅") ? c.green : c.red, marginBottom: 12 }}>
                      {lint}
                    </div>
                  )}
                </div>
              )}

              {/* Feedback */}
              {feedback && (
                <div style={{ background: feedback.correct ? "#14532d55" : "#450a0a55", border: `1px solid ${feedback.correct ? "#166534" : "#7f1d1d"}`, borderRadius: 8, padding: 16, marginBottom: 4 }}>
                  <div style={{ fontWeight: 600, marginBottom: 6, color: feedback.correct ? c.green : c.red }}>
                    {feedback.correct ? "✓ Correct" : "✗ Incorrect"}
                  </div>
                  <div style={{ fontSize: 14, color: c.subtext, lineHeight: 1.6 }}>{feedback.text}</div>
                </div>
              )}

              {!feedback && (
                <button style={{ ...st.btn, marginTop: 8 }} onClick={submitAnswer} disabled={loading || !selected}>
                  {loading ? "Submitting…" : "Submit Answer →"}
                </button>
              )}

              {err && <p style={{ color: c.red, fontSize: 13, marginTop: 12 }}>{err}</p>}
            </div>
          </div>
        )}

        {/* Complete */}
        {page === "complete" && results && (
          <div style={{ maxWidth: 520 }}>
            <h2 style={{ marginTop: 0, marginBottom: 4 }}>Assessment Complete</h2>
            <p style={{ color: c.subtext, marginBottom: 28 }}>Thanks {results.candidate_name}, your results are in.</p>

            <div style={st.card}>
              <div style={{ textAlign: "center", padding: "24px 0 32px" }}>
                <div style={{ fontSize: 60, fontWeight: 700, color: scoreColor(results.total_score) }}>
                  {Math.round(results.total_score * 100)}%
                </div>
                <div style={{ color: c.subtext, marginTop: 6 }}>Overall Score</div>
              </div>

              <div style={{ borderTop: `1px solid ${c.border}`, paddingTop: 20 }}>
                {Object.entries(results.section_scores).map(([section, score]) => (
                  <div key={section} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 0" }}>
                    <span style={{ color: c.subtext, textTransform: "capitalize", fontSize: 14 }}>{section}</span>
                    <span style={{ fontWeight: 600, color: scoreColor(score as number) }}>
                      {Math.round((score as number) * 100)}%
                    </span>
                  </div>
                ))}
              </div>
            </div>

            <button style={st.btnGhost} onClick={() => nav("home")}>← Back to Home</button>
          </div>
        )}

      </div>
    </div>
  )
}
