import { useState } from 'react'

const MOCK = {
  topics: ["Power Electronics", "Control Systems", "Machines"],
  questions: ["What is SCR?", "Explain PWM technique"],
  evaluation: {
    score: 82,
    coding: 88,
    technical: 79,
    aptitude: 75,
    recommendation: "Strong Hire"
  }
}

export default function App() {
  const [page, setPage] = useState("jd")
  const [jd, setJd] = useState("")
  const [result, setResult] = useState<any>(null)
  const [code, setCode] = useState("// write code")

  function generate() {
    setResult(MOCK)
  }

  return (
    <div style={{display:'flex',height:'100vh',background:'#0b1220',color:'white'}}>

      <div style={{width:220,background:'#111827',padding:10}}>
        <h3>Engine</h3>

        <div onClick={()=>setPage('jd')} style={{padding:10,cursor:'pointer'}}>JD</div>
        <div onClick={()=>setPage('code')} style={{padding:10,cursor:'pointer'}}>Coding</div>
        <div onClick={()=>setPage('eval')} style={{padding:10,cursor:'pointer'}}>Eval</div>
      </div>

      <div style={{flex:1,padding:20}}>

        {page==='jd' && (
          <div>
            <h2>Job Description</h2>
            <textarea
              style={{width:'100%',height:120}}
              value={jd}
              onChange={(e)=>setJd(e.target.value)}
            />

            <button onClick={generate}>Generate</button>

            {result && (
              <div>
                <h3>Topics</h3>
                {result.topics.map((t:string,i:number)=>(
                  <p key={i}>✔ {t}</p>
                ))}

                <h3>Questions</h3>
                {result.questions.map((q:string,i:number)=>(
                  <p key={i}>• {q}</p>
                ))}
              </div>
            )}
          </div>
        )}

        {page==='code' && (
          <div>
            <h2>Coding</h2>
            <textarea
              style={{width:'100%',height:300}}
              value={code}
              onChange={(e)=>setCode(e.target.value)}
            />
          </div>
        )}

        {page==='eval' && result && (
          <div>
            <h2>Evaluation</h2>
            <h1>{result.evaluation.score}%</h1>
            <p>Recommendation: {result.evaluation.recommendation}</p>
          </div>
        )}

      </div>
    </div>
  )
}
