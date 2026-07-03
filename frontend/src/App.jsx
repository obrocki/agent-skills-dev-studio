import React, { useRef, useState } from 'react'
import Tree from './components/Tree.jsx'
import Editor from './components/Editor.jsx'
import Chat from './components/Chat.jsx'
import { api } from './api.js'

const HEALTH_LABEL = {
  idle: 'Azure OpenAI',
  checking: 'Checking\u2026',
  healthy: 'Endpoint healthy',
  unhealthy: 'Endpoint unreachable',
  unconfigured: 'Not configured',
}
const HEALTH_HINT = {
  idle: 'Click to probe the Azure OpenAI endpoint and confirm the chat model is reachable (managed identity).',
  checking: 'Contacting the Azure OpenAI endpoint\u2026',
  healthy: 'The Azure OpenAI model responded. Click to re-check.',
  unhealthy: 'The Azure OpenAI endpoint did not respond. Click to retry.',
  unconfigured: 'Azure OpenAI is not configured. Set the endpoint and model in .env, then re-check.',
}

// Three-column layout: project/prompt tree, skill editor, streaming chat.
export default function App() {
  const [selectedPromptId, setSelectedPromptId] = useState(null)
  const [reloadKey, setReloadKey] = useState(0)
  const [activeSkills, setActiveSkills] = useState([])
  const [health, setHealth] = useState({ status: 'idle', detail: '', endpoint: '', model: '' })
  const [healthBusy, setHealthBusy] = useState(false)
  const [chatWidth, setChatWidth] = useState(480)
  const layoutRef = useRef(null)
  const dragRef = useRef(null)

  // Probe the Azure OpenAI endpoint (managed identity) on demand.
  async function checkHealth() {
    if (healthBusy) return
    setHealthBusy(true)
    setHealth((h) => ({ ...h, status: 'checking' }))
    try {
      const r = await api.checkHealth()
      setHealth({
        status: r.status || 'unhealthy',
        detail: r.detail || '',
        endpoint: r.endpoint || '',
        model: r.model || '',
      })
    } catch (e) {
      setHealth({ status: 'unhealthy', detail: `Could not reach the portal API (${e.message}).`, endpoint: '', model: '' })
    } finally {
      setHealthBusy(false)
    }
  }

  const healthTip = [HEALTH_HINT[health.status], health.detail, health.endpoint && `Endpoint: ${health.endpoint}`]
    .filter(Boolean)
    .join('\n')
  const bump = () => setReloadKey((k) => k + 1)

  // Toggle a prompt in/out of the agent's active skill set (tracked by id).
  function toggleSkill(prompt) {
    setActiveSkills((cur) =>
      cur.some((s) => s.id === prompt.id)
        ? cur.filter((s) => s.id !== prompt.id)
        : [...cur, { id: prompt.id, name: prompt.name }]
    )
  }
  const activeIds = new Set(activeSkills.map((s) => s.id))

  // Drag the gutter between the editor and chat columns: dragging left widens
  // the chat/evaluations panel and narrows the skill editor.
  function startResize(e) {
    e.preventDefault()
    dragRef.current = { startX: e.clientX, startWidth: chatWidth }
    e.currentTarget.setPointerCapture(e.pointerId)
  }
  function onResize(e) {
    if (!dragRef.current) return
    const max = Math.max(360, (layoutRef.current?.clientWidth || 1280) - 710)
    const next = dragRef.current.startWidth - (e.clientX - dragRef.current.startX)
    setChatWidth(Math.round(Math.max(360, Math.min(max, next))))
  }
  function endResize(e) {
    if (!dragRef.current) return
    dragRef.current = null
    try {
      e.currentTarget.releasePointerCapture(e.pointerId)
    } catch (_) {
      /* pointer already released */
    }
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2.5l1.9 4.7 4.7 1.9-4.7 1.9L12 15.7l-1.9-4.7L5.4 9.1l4.7-1.9z" />
              <path d="M18.5 13.5l.9 2.3 2.3.9-2.3.9-.9 2.3-.9-2.3-2.3-.9 2.3-.9z" />
            </svg>
          </span>
          <div className="brand-text">
            <span className="brand-title">Agent Skills Dev Studio</span>
            <span className="brand-sub">Author, validate &amp; test agent skills</span>
          </div>
        </div>
        <div className="topbar-meta">
          <button
            type="button"
            className={`pill pill-health status-${health.status}`}
            onClick={checkHealth}
            disabled={healthBusy}
            title={healthTip}
            aria-label={`Azure OpenAI endpoint status: ${HEALTH_LABEL[health.status]}`}
          >
            <span className="pill-dot" aria-hidden="true" />
            {HEALTH_LABEL[health.status]}
          </button>
        </div>
      </header>
      <div
        className="layout"
        ref={layoutRef}
        style={{ gridTemplateColumns: `300px minmax(320px, 1fr) 6px ${chatWidth}px` }}
      >
        <Tree
          selectedPromptId={selectedPromptId}
          onSelectPrompt={setSelectedPromptId}
          activeIds={activeIds}
          onToggleActive={toggleSkill}
          reloadKey={reloadKey}
          onChange={bump}
        />
        <Editor promptId={selectedPromptId} onSaved={bump} />
        <div
          className="col-gutter"
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize chat panel"
          title="Drag to resize the chat panel"
          onPointerDown={startResize}
          onPointerMove={onResize}
          onPointerUp={endResize}
          onPointerCancel={endResize}
        />
        <Chat activeSkills={activeSkills} />
      </div>
    </div>
  )
}
