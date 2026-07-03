import React, { useEffect, useState } from 'react'
import { api } from '../api.js'
import {
  NAME_HELP,
  DESCRIPTION_HELP,
  CONTENT_HELP,
  NAME_PLACEHOLDER,
  DESCRIPTION_PLACEHOLDER,
  CONTENT_PLACEHOLDER,
  CODE_HELP,
  CODE_PLACEHOLDER,
} from '../tooltips.js'

// Naive Markdown preview: headings, bold, and line breaks. Kept minimal for the MVP.
function renderMarkdown(text) {
  const escaped = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  return escaped
    .replace(/^### (.*)$/gm, '<h3>$1</h3>')
    .replace(/^## (.*)$/gm, '<h2>$1</h2>')
    .replace(/^# (.*)$/gm, '<h1>$1</h1>')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br/>')
}

// Best-practices rating bar (red -> green) with a per-check breakdown.
function Validation({ validation }) {
  if (!validation) return null
  return (
    <div className="validation">
      <div className="val-head">
        <span>Best-practices rating</span>
        <span className="val-score" style={{ color: validation.color }}>
          {validation.score}/100 · {validation.rating}
        </span>
      </div>
      <div className="val-bar">
        <div
          className="val-fill"
          style={{ width: `${validation.score}%`, background: validation.color }}
        />
      </div>
      <ul className="checks">
        {validation.checks.map((c) => (
          <li key={c.id} title={c.detail}>
            <span className={`dot ${c.status}`} />
            <span>{c.label}</span>
            {c.status !== 'pass' && c.detail ? (
              <span className="check-detail">— {c.detail}</span>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  )
}

// Center column: edit name, description, and Markdown body for the selected prompt.
export default function Editor({ promptId, onSaved }) {
  const [prompt, setPrompt] = useState(null)
  const [status, setStatus] = useState('')
  const [validation, setValidation] = useState(null)
  const [versions, setVersions] = useState([])
  const [pendingDelete, setPendingDelete] = useState(null)

  useEffect(() => {
    setValidation(null)
    setPendingDelete(null)
    if (!promptId) {
      setPrompt(null)
      setVersions([])
      return
    }
    api.getPrompt(promptId).then(setPrompt)
    api.listVersions(promptId).then(setVersions)
  }, [promptId])

  // Re-validate whenever the editable fields change (typing, loading a version,
  // or switching prompts) so the score and checks always match the live draft.
  useEffect(() => {
    if (!prompt) {
      setValidation(null)
      return
    }
    let cancelled = false
    const draft = {
      name: prompt.name,
      description: prompt.description,
      content: prompt.content,
    }
    const timer = setTimeout(() => {
      api.validateDraft(draft).then((v) => {
        if (!cancelled) setValidation(v)
      })
    }, 200)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [prompt?.name, prompt?.description, prompt?.content])

  // Allow Escape to dismiss the delete-confirmation overlay.
  useEffect(() => {
    if (!pendingDelete) return
    function onKey(e) {
      if (e.key === 'Escape') setPendingDelete(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [pendingDelete])

  if (!prompt) {
    return (
      <div className="editor empty">
        <div className="panel-head">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M12 20h9" />
            <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4z" />
          </svg>
          <span>Skill editor</span>
        </div>
        <div className="empty-state">
          <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <path d="M14 2v6h6" />
          </svg>
          <p>Select a skill from the left to edit it.</p>
        </div>
      </div>
    )
  }

  async function save() {
    const result = await api.updatePrompt(prompt)
    setPrompt(result.prompt)
    setValidation(result.validation)
    setStatus(`Saved · v${result.version.version}`)
    const list = await api.listVersions(prompt.id)
    setVersions(list)
    onSaved()
    setTimeout(() => setStatus(''), 2500)
  }

  function loadVersion(v) {
    setPrompt({ ...prompt, name: v.name, description: v.description, content: v.content, code: v.code })
    setStatus(`Loaded v${v.version} — Save to keep`)
  }

  async function confirmDelete() {
    const target = pendingDelete
    if (!target) return
    await api.deleteVersion(prompt.id, target.id)
    setPendingDelete(null)
    const list = await api.listVersions(prompt.id)
    setVersions(list)
    setStatus(`Deleted version ${target.version}`)
    setTimeout(() => setStatus(''), 2500)
  }

  return (
    <div className="editor">
      <div className="panel-head">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M12 20h9" />
          <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4z" />
        </svg>
        <span>Skill editor</span>
      </div>
      <label title={NAME_HELP}>Name (hover for rules)</label>
      <input
        value={prompt.name}
        placeholder={NAME_PLACEHOLDER}
        onChange={(e) => setPrompt({ ...prompt, name: e.target.value })}
      />
      <label title={DESCRIPTION_HELP}>Description (hover for rules)</label>
      <textarea
        className="desc"
        value={prompt.description}
        placeholder={DESCRIPTION_PLACEHOLDER}
        onChange={(e) => setPrompt({ ...prompt, description: e.target.value })}
      />
      <label title={CONTENT_HELP}>Markdown body (hover for rules)</label>
      <div className="md-split">
        <textarea
          value={prompt.content}
          placeholder={CONTENT_PLACEHOLDER}
          onChange={(e) => setPrompt({ ...prompt, content: e.target.value })}
        />
        <div
          className="preview"
          dangerouslySetInnerHTML={{ __html: renderMarkdown(prompt.content) }}
        />
      </div>
      <label title={CODE_HELP}>Python code (optional — runs as a tool)</label>
      <textarea
        className="code-editor"
        value={prompt.code || ''}
        placeholder={CODE_PLACEHOLDER}
        spellCheck={false}
        onChange={(e) => setPrompt({ ...prompt, code: e.target.value })}
      />
      <div className="editor-actions">
        <button onClick={save}>Save</button>
        <span>{status}</span>
      </div>
      <Validation validation={validation} />
      <div className="versions">
        <h4>Version history</h4>
        {versions.length === 0 ? (
          <p className="check-detail">No versions yet — save to create one.</p>
        ) : (
          <ul>
            {versions.map((v) => (
              <li key={v.id}>
                <span className="v-meta">{v.version}</span>
                <span>
                  <span className="v-score">{v.score}/100</span>
                  <button onClick={() => loadVersion(v)}>Load</button>
                  <button
                    className="icon"
                    title="Delete this version"
                    aria-label={`Delete version ${v.version}`}
                    onClick={() => setPendingDelete(v)}
                  >
                    ×
                  </button>
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
      {pendingDelete && (
        <div
          className="modal-overlay"
          role="presentation"
          onClick={() => setPendingDelete(null)}
        >
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="confirm-delete-title"
            onClick={(e) => e.stopPropagation()}
          >
            <h4 id="confirm-delete-title">Delete this version?</h4>
            <p>
              Permanently remove the snapshot from{' '}
              <strong>{pendingDelete.version}</strong> ({pendingDelete.score}/100).
              This can't be undone.
            </p>
            <div className="modal-actions">
              <button className="btn-ghost" onClick={() => setPendingDelete(null)}>
                Cancel
              </button>
              <button className="btn-danger" onClick={confirmDelete}>
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
