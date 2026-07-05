import React, { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api.js'

const RUN_EVAL_ORDER = ['skill', 'task', 'tools']

function formatTimestamp(value) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

function turnLabel(turn, revisionName) {
  const text = (turn.query || '').trim()
  const snippet = text.length > 42 ? `${text.slice(0, 42)}…` : text || 'Untitled turn'
  return `${revisionName || 'Revision'} · ${snippet} · ${formatTimestamp(turn.created_at)}`
}

// Right column: pick one or more active skills (left checkboxes), see how they
// combine, check them for conflicts, and stream a reply from the multi-skill agent.
export default function Chat({ activeSkills }) {
  const [q, setQ] = useState('')
  const [messages, setMessages] = useState([])
  const [busy, setBusy] = useState(false)
  const [evalResult, setEvalResult] = useState(null)
  const [evalBusy, setEvalBusy] = useState(false)
  const [logs, setLogs] = useState([])
  const [evals, setEvals] = useState([])
  const [revisions, setRevisions] = useState([])
  const [allTurns, setAllTurns] = useState([])
  const [revisionTurns, setRevisionTurns] = useState([])
  const [selectedRevisionId, setSelectedRevisionId] = useState('')
  const [compareIds, setCompareIds] = useState({ baseline: '', candidate: '' })
  const [comparison, setComparison] = useState(null)
  const [historyBusy, setHistoryBusy] = useState(false)
  const [renameDraft, setRenameDraft] = useState('')
  const [renameBusy, setRenameBusy] = useState(false)
  const [historyStatus, setHistoryStatus] = useState('')
  const outRef = useRef(null)
  const logsRef = useRef(null)

  const pushLog = (level, msg) =>
    setLogs((prev) => [
      ...prev,
      { level, msg, time: new Date().toLocaleTimeString() },
    ])

  const activeIds = activeSkills.map((s) => s.id)
  const activeKey = activeIds.join(',')
  const hasSkills = activeIds.length > 0
  const selectedRevision = revisions.find((revision) => revision.id === selectedRevisionId) || null
  const revisionNameById = useMemo(
    () => Object.fromEntries(revisions.map((revision) => [revision.id, revision.name])),
    [revisions]
  )

  async function refreshHistory(preferredRevisionId) {
    setHistoryBusy(true)
    try {
      const [nextRevisions, nextTurns] = await Promise.all([
        api.listAgentRevisions(),
        api.listChatTurns(),
      ])
      setRevisions(nextRevisions)
      setAllTurns(nextTurns)
      setSelectedRevisionId((current) => {
        const preferred = preferredRevisionId || current
        if (preferred && nextRevisions.some((revision) => revision.id === preferred)) {
          return preferred
        }
        return nextRevisions[0]?.id || ''
      })
    } finally {
      setHistoryBusy(false)
    }
  }

  useEffect(() => {
    refreshHistory()
  }, [])

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

  // Keep the newest activity entry in view as execution updates stream in.
  useEffect(() => {
    const el = logsRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [logs])

  useEffect(() => {
    if (!selectedRevisionId) {
      setRevisionTurns([])
      setRenameDraft('')
      return
    }
    setRenameDraft(selectedRevision?.name || '')
    api.listChatTurns(selectedRevisionId).then(setRevisionTurns).catch(() => setRevisionTurns([]))
  }, [selectedRevisionId, selectedRevision?.name])

  useEffect(() => {
    if (!compareIds.baseline || !compareIds.candidate || compareIds.baseline === compareIds.candidate) {
      setComparison(null)
      return
    }
    let cancelled = false
    api.compareChatTurns(compareIds.baseline, compareIds.candidate)
      .then((result) => {
        if (!cancelled) setComparison(result)
      })
      .catch(() => {
        if (!cancelled) setComparison(null)
      })
    return () => {
      cancelled = true
    }
  }, [compareIds])

  async function renameRevision() {
    const nextName = renameDraft.trim()
    if (!selectedRevisionId || !nextName) return
    setRenameBusy(true)
    try {
      await api.renameAgentRevision(selectedRevisionId, nextName)
      setHistoryStatus(`Renamed revision to ${nextName}.`)
      await refreshHistory(selectedRevisionId)
    } finally {
      setRenameBusy(false)
    }
  }

  function send() {
    if (!hasSkills || busy || !q.trim()) return
    const userText = q.trim()
    setQ('')
    setHistoryStatus('')
    // Show the user's message immediately, with an empty assistant bubble to stream into.
    setMessages((prev) => [...prev, { role: 'user', text: userText }, { role: 'assistant', text: '' }])
    setBusy(true)
    setEvals([])
    pushLog('send', `Sent: ${userText}`)

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
    params.append('time_zone', Intl.DateTimeFormat().resolvedOptions().timeZone)
    params.append('locale', navigator.language)
    const es = new EventSource(`/api/chat?${params.toString()}`)
    let finished = false

    // Execution updates travel on a dedicated `log` event so they never mix
    // into the assistant message that `onmessage` assembles.
    es.addEventListener('log', (e) => {
      try {
        const d = JSON.parse(e.data)
        pushLog(d.level || 'info', d.msg || '')
      } catch {
        /* ignore a malformed log frame */
      }
    })
    // Evaluation cards arrive on a dedicated `eval` event; replace any prior
    // card with the same key so late frames update in place.
    es.addEventListener('eval', (e) => {
      try {
        const d = JSON.parse(e.data)
        setEvals((prev) => [...prev.filter((x) => x.key !== d.key), d])
      } catch {
        /* ignore malformed eval frame */
      }
    })
    es.addEventListener('history', (e) => {
      try {
        const d = JSON.parse(e.data)
        setHistoryStatus(`Saved run to ${d.revision.name}.`)
        setSelectedRevisionId(d.revision.id)
        setCompareIds((prev) => ({
          baseline: prev.baseline || d.turn.id,
          candidate: prev.candidate,
        }))
        refreshHistory(d.revision.id)
      } catch {
        /* ignore malformed history frame */
      }
    })
    es.onopen = () => pushLog('info', 'Connected to agent stream.')
    es.onmessage = (e) => {
      if (e.data === '[DONE]') {
        finished = true
        es.close()
        setBusy(false)
        return
      }
      if (e.data === '[ERROR]') {
        finished = true
        es.close()
        setBusy(false)
        appendToReply('\n[chat failed]')
        return
      }
      appendToReply(e.data)
    }
    es.onerror = () => {
      es.close()
      if (!finished) pushLog('error', 'Stream disconnected.')
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

      <div className="history-shell">
        <div className="history-browser">
          <div className="history-head">
            <span>Agent revisions</span>
            <span className="logs-count">{historyBusy ? '…' : revisions.length}</span>
          </div>
          {historyStatus ? <p className="history-status">{historyStatus}</p> : null}
          {revisions.length === 0 ? (
            <p className="logs-empty">Completed runs create revisions automatically.</p>
          ) : (
            <div className="revision-list">
              {revisions.map((revision) => (
                <button
                  key={revision.id}
                  type="button"
                  className={`revision-card ${revision.id === selectedRevisionId ? 'active' : ''}`}
                  onClick={() => setSelectedRevisionId(revision.id)}
                >
                  <span className="revision-name">{revision.name}</span>
                  <span className="revision-meta">
                    {revision.turn_count} turn{revision.turn_count === 1 ? '' : 's'} · {formatTimestamp(revision.last_run_at || revision.updated_at)}
                  </span>
                  <span className="revision-metrics">
                    <MetricPill label="compat" value={revision.scores?.pre_run} />
                    <MetricPill label="skill" value={revision.scores?.skill} />
                    <MetricPill label="task" value={revision.scores?.task} />
                    <MetricPill label="tools" value={revision.scores?.tools} />
                  </span>
                </button>
              ))}
            </div>
          )}
          {selectedRevision && (
            <div className="revision-detail">
              <div className="history-head compact">
                <span>Selected revision</span>
              </div>
              <div className="rename-row">
                <input
                  value={renameDraft}
                  onChange={(e) => setRenameDraft(e.target.value)}
                  aria-label="Revision name"
                />
                <button type="button" onClick={renameRevision} disabled={renameBusy || !renameDraft.trim()}>
                  Rename
                </button>
              </div>
              <div className="chips small">
                {selectedRevision.prompt_names.map((name, index) => (
                  <span key={`${name}-${index}`} className="chip">{name}</span>
                ))}
              </div>
              {selectedRevision.tool_names?.length > 0 ? (
                <p className="history-note">Tools: {selectedRevision.tool_names.join(', ')}</p>
              ) : (
                <p className="history-note">Tools: none</p>
              )}
            </div>
          )}
        </div>

        <div className="turn-browser">
          <div className="history-head">
            <span>Saved turns</span>
            <span className="logs-count">{selectedRevisionId ? revisionTurns.length : 0}</span>
          </div>
          {!selectedRevisionId ? (
            <p className="logs-empty">Select a revision to inspect its runs.</p>
          ) : revisionTurns.length === 0 ? (
            <p className="logs-empty">No turns saved for this revision yet.</p>
          ) : (
            <div className="turn-list">
              {revisionTurns.map((turn) => (
                <div key={turn.id} className="turn-row">
                  <button
                    type="button"
                    className="turn-card"
                    onClick={() => setCompareIds((prev) => ({ ...prev, baseline: turn.id }))}
                  >
                    <span className="turn-query">{turn.query}</span>
                    <span className="turn-meta">{formatTimestamp(turn.created_at)}</span>
                  </button>
                  <div className="turn-actions">
                    <button type="button" onClick={() => setCompareIds((prev) => ({ ...prev, baseline: turn.id }))}>
                      Baseline
                    </button>
                    <button type="button" onClick={() => setCompareIds((prev) => ({ ...prev, candidate: turn.id }))}>
                      Candidate
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <details className="compare-drawer panel-collapse" open={allTurns.length >= 2 ? true : undefined}>
        <summary>
          <span className="collapse-caret" aria-hidden="true" />
          <span>Turn comparison</span>
        </summary>
        {allTurns.length < 2 ? (
          <p className="check-detail">Run the agent at least twice to compare saved turns.</p>
        ) : (
          <>
            <div className="compare-picks">
              <label>
                Baseline
                <select
                  value={compareIds.baseline}
                  onChange={(e) => setCompareIds((prev) => ({ ...prev, baseline: e.target.value }))}
                >
                  <option value="">Select a turn…</option>
                  {allTurns.map((turn) => (
                    <option key={turn.id} value={turn.id}>
                      {turnLabel(turn, revisionNameById[turn.revision_id])}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Candidate
                <select
                  value={compareIds.candidate}
                  onChange={(e) => setCompareIds((prev) => ({ ...prev, candidate: e.target.value }))}
                >
                  <option value="">Select a turn…</option>
                  {allTurns.map((turn) => (
                    <option key={turn.id} value={turn.id}>
                      {turnLabel(turn, revisionNameById[turn.revision_id])}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            {comparison && (
              <>
                <div className="compare-summary">
                  <MetricDelta label="compatibility" value={comparison.delta.pre_run_score.delta} />
                  <MetricDelta label="tool calls" value={comparison.delta.tool_calls.delta} />
                  {comparison.delta.evaluations.map((item) => (
                    <MetricDelta key={item.key} label={item.title} value={item.delta} />
                  ))}
                </div>
                <div className="compare-grid">
                  <TurnPanel
                    title={`Baseline · ${revisionNameById[comparison.baseline.revision_id] || 'Revision'}`}
                    turn={comparison.baseline}
                  />
                  <TurnPanel
                    title={`Candidate · ${revisionNameById[comparison.candidate.revision_id] || 'Revision'}`}
                    turn={comparison.candidate}
                  />
                </div>
              </>
            )}
          </>
        )}
      </details>

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

      <div className="chat-logs">
        <div className="logs-head">
          <span className="logs-title">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M4 6h16M4 12h16M4 18h10" />
            </svg>
            Activity log
          </span>
          <div className="logs-actions">
            <span className="logs-count" aria-label={`${logs.length} log entries`}>{logs.length}</span>
            <button
              type="button"
              className="logs-clear"
              onClick={() => setLogs([])}
              disabled={logs.length === 0}
            >
              Clear
            </button>
          </div>
        </div>
        <div
          className="logs-body"
          ref={logsRef}
          role="log"
          aria-live="polite"
          aria-label="Agent execution activity"
        >
          {logs.length === 0 ? (
            <p className="logs-empty">Live execution updates appear here when you run the agent.</p>
          ) : (
            logs.map((l, i) => (
              <div key={i} className={`log-line log-${l.level}`}>
                <span className="log-dot" aria-hidden="true" />
                <time className="log-time">{l.time}</time>
                <span className="log-msg">{l.msg}</span>
              </div>
            ))
          )}
        </div>
      </div>

      {evals.length > 0 && (
        <div className="evals">
          <div className="evals-head"><span>Run evaluations</span></div>
          {RUN_EVAL_ORDER
            .map((k) => evals.find((e) => e.key === k))
            .filter(Boolean)
            .map((ev) => <ConflictReport key={ev.key} title={ev.title} result={ev} />)}
        </div>
      )}
    </div>
  )
}

function MetricPill({ label, value }) {
  return (
    <span className="metric-pill">
      <strong>{label}</strong> {value == null ? '—' : value}
    </span>
  )
}

function MetricDelta({ label, value }) {
  const cls = value == null ? 'same' : value > 0 ? 'better' : value < 0 ? 'worse' : 'same'
  const text = value == null ? '—' : value > 0 ? `+${value}` : `${value}`
  return (
    <span className={`metric-delta ${cls}`}>
      <strong>{label}</strong> {text}
    </span>
  )
}

function TurnPanel({ title, turn }) {
  const evaluations = RUN_EVAL_ORDER
    .map((key) => turn.evaluations.find((item) => item.key === key))
    .filter(Boolean)
  return (
    <div className="turn-panel">
      <div className="history-head compact">
        <span>{title}</span>
      </div>
      <p className="turn-meta">{formatTimestamp(turn.created_at)}</p>
      <div className="turn-block">
        <strong>Prompt</strong>
        <p>{turn.query}</p>
      </div>
      <div className="turn-block">
        <strong>Reply</strong>
        <p>{turn.answer}</p>
      </div>
      <div className="turn-block">
        <strong>Prompt snapshots</strong>
        <ul className="mini-list">
          {turn.prompt_versions.map((item) => (
            <li key={item.version_id}>{item.prompt_name} · {item.version}</li>
          ))}
        </ul>
      </div>
      <div className="turn-block">
        <strong>Tool calls</strong>
        {turn.tool_calls.length === 0 ? (
          <p>None</p>
        ) : (
          <ul className="mini-list">
            {turn.tool_calls.map((item) => (
              <li key={item.call_id}>{item.name || 'tool'}{item.error ? ` · ${item.error}` : ''}</li>
            ))}
          </ul>
        )}
      </div>
      <ConflictReport title="Skill compatibility" result={turn.pre_run_evaluation} />
      {evaluations.map((item) => (
        <ConflictReport key={item.key} title={item.title} result={item} />
      ))}
    </div>
  )
}

// Compatibility score + findings for the active skill combination.
function ConflictReport({ busy, result, title = 'Skill compatibility' }) {
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
        <span>{title}</span>
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
