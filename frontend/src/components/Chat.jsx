import React, { useEffect, useRef, useState } from 'react'
import { api } from '../api.js'

// Right column: pick one or more active skills (left checkboxes), see how they
// combine, check them for conflicts, and stream a reply from the multi-skill agent.
export default function Chat({ activeSkills }) {
  const [q, setQ] = useState('')
  const [messages, setMessages] = useState([])
  const [busy, setBusy] = useState(false)
  const [evalResult, setEvalResult] = useState(null)
  const [evalBusy, setEvalBusy] = useState(false)
  const outRef = useRef(null)

  const activeIds = activeSkills.map((s) => s.id)
  const activeKey = activeIds.join(',')
  const hasSkills = activeIds.length > 0

  // Re-check skill compatibility (debounced) whenever the active set changes.
  useEffect(() => {
    if (activeKey.split(',').filter(Boolean).length < 2) {
      setEvalResult(null)
      setEvalBusy(false)
      return
    }
    setEvalBusy(true)
    const ids = activeKey.split(',')
    const t = setTimeout(async () => {
      try {
        setEvalResult(await api.evaluateAgent(ids))
      } catch {
        setEvalResult(null)
      } finally {
        setEvalBusy(false)
      }
    }, 400)
    return () => clearTimeout(t)
  }, [activeKey])

  // Keep the latest message in view as the conversation grows / streams.
  useEffect(() => {
    const el = outRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages])

  function send() {
    if (!hasSkills || busy || !q.trim()) return
    const userText = q.trim()
    setQ('')
    // Show the user's message immediately, with an empty assistant bubble to stream into.
    setMessages((prev) => [...prev, { role: 'user', text: userText }, { role: 'assistant', text: '' }])
    setBusy(true)

    const appendToReply = (chunk) =>
      setMessages((prev) => {
        const next = prev.slice()
        const last = next[next.length - 1]
        if (last && last.role === 'assistant') next[next.length - 1] = { ...last, text: last.text + chunk }
        return next
      })

    const params = new URLSearchParams()
    activeIds.forEach((id) => params.append('prompt_ids', id))
    params.append('q', userText)
    const es = new EventSource(`/api/chat?${params.toString()}`)
    es.onmessage = (e) => {
      if (e.data === '[DONE]') {
        es.close()
        setBusy(false)
        return
      }
      if (e.data === '[ERROR]') {
        es.close()
        setBusy(false)
        appendToReply('\n[chat failed]')
        return
      }
      appendToReply(e.data)
    }
    es.onerror = () => {
      es.close()
      setBusy(false)
    }
  }

  return (
    <div className="chat">
      <div className="panel-head">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M21 11.5a8.5 8.5 0 0 1-12.3 7.6L3 21l1.9-5.7A8.5 8.5 0 1 1 21 11.5z" />
        </svg>
        <span>Test chat</span>
      </div>

      <div className="combined">
        <div className="combined-head">
          <span className="combined-title">
            Agent skills
            <span
              className="info"
              tabIndex={0}
              role="img"
              aria-label="How skill evaluation works"
              title={
                'Before you run the agent, every active skill is reviewed together by an AI judge. '
                + 'It scores how well they combine (0–100) and flags conflicts, contradictions, '
                + 'overlaps, and gaps between them. Runs automatically whenever two or more skills are active.'
              }
            >
              i
            </span>
          </span>
          <span className="combined-count">{activeIds.length} active</span>
        </div>
        {hasSkills ? (
          <div className="chips">
            {activeSkills.map((s) => (
              <span key={s.id} className="chip">{s.name}</span>
            ))}
          </div>
        ) : (
          <p className="empty-hint">Tick one or more skills on the left to build the agent.</p>
        )}
        {activeIds.length >= 2 && <ConflictReport busy={evalBusy} result={evalResult} />}
      </div>

      <div className="chat-out" ref={outRef}>
        {messages.length === 0 && !busy && (
          <div className="chat-empty">
            <span className="chat-empty-mark" aria-hidden="true">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 11.5a8.5 8.5 0 0 1-12.3 7.6L3 21l1.9-5.7A8.5 8.5 0 1 1 21 11.5z" />
              </svg>
            </span>
            <p>{hasSkills ? 'Try out the agent' : 'No skills active'}</p>
            <span>{hasSkills ? 'Ask a question below — the agent uses every active skill.' : 'Tick at least one skill on the left.'}</span>
          </div>
        )}
        {messages.map((m, i) => {
          const streaming = m.role === 'assistant' && !m.text && busy && i === messages.length - 1
          if (streaming) {
            return (
              <div key={i} className="typing" aria-label="Assistant is responding">
                <span></span>
                <span></span>
                <span></span>
              </div>
            )
          }
          if (m.role === 'assistant' && !m.text) return null
          return (
            <div key={i} className={`msg msg-${m.role}`}>{m.text}</div>
          )
        })}
      </div>

      <div className="chat-in">
        <input
          value={q}
          placeholder={hasSkills ? 'Ask the agent...' : 'Activate a skill first'}
          disabled={!hasSkills}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && send()}
        />
        <button onClick={send} disabled={!hasSkills || busy}>
          Send
        </button>
      </div>
    </div>
  )
}

// Compatibility score + findings for the active skill combination.
function ConflictReport({ busy, result }) {
  if (busy && !result) {
    return (
      <div className="conflict conflict-loading">
        <span className="typing" aria-label="Checking for conflicts">
          <span></span><span></span><span></span>
        </span>
        Checking skill compatibility…
      </div>
    )
  }
  if (!result) return null

  const unavailable = result.score == null
  return (
    <div className="conflict">
      <div className="val-head">
        <span>Skill compatibility</span>
        <span className="val-score">{unavailable ? '—' : `${result.score}/100`}</span>
      </div>
      {!unavailable && (
        <div className="val-bar">
          <div className="val-fill" style={{ width: `${result.score}%`, background: result.color }} />
        </div>
      )}
      <p className="conflict-summary">
        <strong>{result.rating}</strong>
        {result.summary ? ` — ${result.summary}` : ''}
      </p>
      {result.findings && result.findings.length > 0 && (
        <ul className="findings">
          {result.findings.map((f, i) => (
            <li key={i} className="finding">
              <span className={`tag ${f.type}`}>{f.type}</span>
              <span className="finding-detail">
                {f.skills && f.skills.length ? <em>{f.skills.join(' ↔ ')}: </em> : null}
                {f.detail}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
