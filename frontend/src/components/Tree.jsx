import React, { useEffect, useRef, useState } from 'react'
import { api } from '../api.js'

// Recognised skill source files: Markdown becomes the skill body, Python the code.
const MD_EXT = /\.(md|markdown|mdown|mkd|mdx)$/i
const PY_EXT = /\.py$/i
const stripExt = (name) => name.replace(/\.[^./\\]+$/, '')

// Turn a set of dropped files into skill drafts. A Markdown and a Python file
// that share a base name (or are the only pair dropped) combine into one skill;
// otherwise each Markdown or Python file becomes its own skill.
async function filesToSkills(files) {
  const md = files.filter((f) => MD_EXT.test(f.name))
  const py = files.filter((f) => PY_EXT.test(f.name))

  // Simple, common case: one Markdown + one Python pair into a single skill,
  // even when their filenames differ.
  if (md.length === 1 && py.length === 1) {
    return [
      {
        name: stripExt(md[0].name) || 'Untitled skill',
        content: await md[0].text(),
        code: await py[0].text(),
      },
    ]
  }

  // Otherwise group by base filename so like-named files pair up.
  const groups = new Map()
  const order = []
  for (const file of files) {
    const isMd = MD_EXT.test(file.name)
    const isPy = PY_EXT.test(file.name)
    if (!isMd && !isPy) continue
    const base = stripExt(file.name)
    const key = base.toLowerCase()
    if (!groups.has(key)) {
      groups.set(key, { name: base || 'Untitled skill', content: '', code: '' })
      order.push(key)
    }
    const text = await file.text()
    if (isMd) groups.get(key).content = text
    else groups.get(key).code = text
  }
  return order.map((k) => groups.get(k))
}

// Left column: projects expand into prompts. Selecting a prompt loads it center.
// Uses inline inputs (no window.prompt, which is blocked in embedded browsers).
export default function Tree({ selectedPromptId, onSelectPrompt, activeIds, onToggleActive, reloadKey, onChange }) {
  const [projects, setProjects] = useState([])
  const [promptsByProject, setPromptsByProject] = useState({})
  const [newProject, setNewProject] = useState('')
  const [promptDrafts, setPromptDrafts] = useState({})
  const [dragProjectId, setDragProjectId] = useState(null)
  const fileInputs = useRef({})

  async function loadProjects() {
    const list = await api.listProjects()
    setProjects(list)
    const entries = await Promise.all(
      list.map(async (p) => [p.id, await api.listPrompts(p.id)])
    )
    setPromptsByProject(Object.fromEntries(entries))
  }

  useEffect(() => {
    loadProjects()
  }, [reloadKey])

  async function addProject() {
    const name = newProject.trim()
    if (!name) return
    await api.createProject(name)
    setNewProject('')
    loadProjects()
  }

  async function removeProject(id) {
    await api.deleteProject(id)
    onChange()
    loadProjects()
  }

  async function addPrompt(projectId) {
    const name = (promptDrafts[projectId] || '').trim()
    if (!name) return
    await api.createPrompt(projectId, name)
    setPromptDrafts((d) => ({ ...d, [projectId]: '' }))
    loadProjects()
  }

  // Create one or more skills from dropped (or browsed) Markdown/Python files.
  // The file name becomes the skill name and can be renamed later in the editor.
  async function createSkillsFromFiles(projectId, fileList) {
    const files = Array.from(fileList || [])
    if (!files.length) return
    const skills = await filesToSkills(files)
    if (!skills.length) return
    let firstId = null
    for (const skill of skills) {
      const created = await api.createPrompt(projectId, skill.name, {
        content: skill.content,
        code: skill.code,
      })
      if (!firstId) firstId = created.id
    }
    await loadProjects()
    if (firstId) onSelectPrompt(firstId)
    onChange()
  }

  function onDropFiles(projectId, e) {
    e.preventDefault()
    setDragProjectId(null)
    createSkillsFromFiles(projectId, e.dataTransfer?.files)
  }

  async function removePrompt(id) {
    await api.deletePrompt(id)
    if (activeIds.has(id)) onToggleActive({ id, name: '' })
    onChange()
    loadProjects()
  }

  return (
    <div className="tree">
      <div className="panel-head">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M3 7a2 2 0 0 1 2-2h3l2 2h7a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
        </svg>
        <span>Projects</span>
      </div>
      <div className="add-row">
        <input
          value={newProject}
          placeholder="New project name"
          onChange={(e) => setNewProject(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && addProject()}
        />
        <button onClick={addProject} disabled={!newProject.trim()}>
          + Project
        </button>
      </div>
      {projects.length === 0 && (
        <p className="empty-hint">No projects yet — create one above to get started.</p>
      )}
      {projects.map((proj) => (
        <div key={proj.id} className="project">
          <div className="project-row">
            <strong>{proj.name}</strong>
            <button
              className="icon"
              title="Delete project"
              aria-label={`Delete project ${proj.name}`}
              onClick={() => removeProject(proj.id)}
            >
              ×
            </button>
          </div>
          <ul>
            {(promptsByProject[proj.id] || []).map((pr) => (
              <li
                key={pr.id}
                className={pr.id === selectedPromptId ? 'active' : ''}
              >
                <input
                  type="checkbox"
                  className="skill-check"
                  checked={activeIds.has(pr.id)}
                  title="Include this skill in the agent"
                  aria-label={`Include skill ${pr.name} in the agent`}
                  onClick={(e) => e.stopPropagation()}
                  onChange={() => onToggleActive(pr)}
                />
                <span className="skill-name" onClick={() => onSelectPrompt(pr.id)}>
                  {pr.name}
                </span>
                <button
                  className="icon"
                  title="Delete skill"
                  aria-label={`Delete skill ${pr.name}`}
                  onClick={(e) => {
                    e.stopPropagation()
                    removePrompt(pr.id)
                  }}
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
          <div className="add-row">
            <input
              value={promptDrafts[proj.id] || ''}
              placeholder="New skill name"
              onChange={(e) => setPromptDrafts((d) => ({ ...d, [proj.id]: e.target.value }))}
              onKeyDown={(e) => e.key === 'Enter' && addPrompt(proj.id)}
            />
            <button onClick={() => addPrompt(proj.id)} disabled={!(promptDrafts[proj.id] || '').trim()}>
              +
            </button>
          </div>
          <div
            className={`drop-zone${dragProjectId === proj.id ? ' dragging' : ''}`}
            role="button"
            tabIndex={0}
            title="Drop a Markdown (.md) file to create a skill, plus an optional Python (.py) file for its code. The file name becomes the skill name — rename it later in the editor."
            aria-label={`Drop Markdown and Python files to add a skill to ${proj.name}`}
            onClick={() => fileInputs.current[proj.id]?.click()}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault()
                fileInputs.current[proj.id]?.click()
              }
            }}
            onDragOver={(e) => {
              e.preventDefault()
              setDragProjectId(proj.id)
            }}
            onDragLeave={(e) => {
              e.preventDefault()
              setDragProjectId((id) => (id === proj.id ? null : id))
            }}
            onDrop={(e) => onDropFiles(proj.id, e)}
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="7 10 12 15 17 10" />
              <line x1="12" y1="15" x2="12" y2="3" />
            </svg>
            <span>
              Drop <strong>.md</strong> + optional <strong>.py</strong> to add a skill
            </span>
            <input
              ref={(el) => {
                fileInputs.current[proj.id] = el
              }}
              type="file"
              multiple
              accept=".md,.markdown,.mdown,.mkd,.mdx,.py"
              hidden
              onChange={(e) => {
                createSkillsFromFiles(proj.id, e.target.files)
                e.target.value = ''
              }}
            />
          </div>
        </div>
      ))}
    </div>
  )
}
