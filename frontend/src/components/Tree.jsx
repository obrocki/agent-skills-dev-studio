import React, { useEffect, useState } from 'react'
import { api } from '../api.js'

// Left column: projects expand into prompts. Selecting a prompt loads it center.
// Uses inline inputs (no window.prompt, which is blocked in embedded browsers).
export default function Tree({ selectedPromptId, onSelectPrompt, activeIds, onToggleActive, reloadKey, onChange }) {
  const [projects, setProjects] = useState([])
  const [promptsByProject, setPromptsByProject] = useState({})
  const [newProject, setNewProject] = useState('')
  const [promptDrafts, setPromptDrafts] = useState({})

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
        </div>
      ))}
    </div>
  )
}
