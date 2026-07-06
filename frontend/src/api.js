// Thin fetch wrappers over the FastAPI CRUD contract (all under /api).

async function jsonOrThrow(res) {
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  if (res.status === 204) return null
  return res.json()
}

export const api = {
  listProjects: () => fetch('/api/projects').then(jsonOrThrow),
  createProject: (name) =>
    fetch('/api/projects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    }).then(jsonOrThrow),
  deleteProject: (id) =>
    fetch(`/api/projects/${id}`, { method: 'DELETE' }).then(jsonOrThrow),
  listPrompts: (projectId) =>
    fetch(`/api/projects/${projectId}/prompts`).then(jsonOrThrow),
  createPrompt: (projectId, name, extra = {}) =>
    fetch('/api/prompts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_id: projectId,
        name,
        description: extra.description || '',
        content: extra.content || '',
        code: extra.code || '',
      }),
    }).then(jsonOrThrow),
  getPrompt: (id) => fetch(`/api/prompts/${id}`).then(jsonOrThrow),
  validatePrompt: (id) => fetch(`/api/prompts/${id}/validate`).then(jsonOrThrow),
  validateDraft: (draft) =>
    fetch('/api/prompts/validate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: draft.name || '',
        description: draft.description || '',
        content: draft.content || '',
      }),
    }).then(jsonOrThrow),
  listVersions: (id) => fetch(`/api/prompts/${id}/versions`).then(jsonOrThrow),
  deleteVersion: (promptId, versionId) =>
    fetch(`/api/prompts/${promptId}/versions/${versionId}`, { method: 'DELETE' }).then(jsonOrThrow),
  updatePrompt: (prompt) =>
    fetch(`/api/prompts/${prompt.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_id: prompt.project_id,
        name: prompt.name,
        description: prompt.description,
        content: prompt.content,
        code: prompt.code || '',
      }),
    }).then(jsonOrThrow),
  evaluateAgent: (promptIds) =>
    fetch('/api/agents/evaluate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt_ids: promptIds }),
    }).then(jsonOrThrow),
  checkHealth: () => fetch('/api/health').then(jsonOrThrow),
  deletePrompt: (id) =>
    fetch(`/api/prompts/${id}`, { method: 'DELETE' }).then(jsonOrThrow),
  listAgentRevisions: (options) => fetch('/api/agent-revisions', options).then(jsonOrThrow),
  renameAgentRevision: (revisionId, name) =>
    fetch(`/api/agent-revisions/${revisionId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    }).then(jsonOrThrow),
  listChatTurns: (revisionId, options) => {
    const query = revisionId ? `?revision_id=${encodeURIComponent(revisionId)}` : ''
    return fetch(`/api/chat-turns${query}`, options).then(jsonOrThrow)
  },
  compareChatTurns: (baselineId, candidateId) =>
    fetch(
      `/api/chat-turns/compare?baseline_id=${encodeURIComponent(baselineId)}&candidate_id=${encodeURIComponent(candidateId)}`
    ).then(jsonOrThrow),
}
