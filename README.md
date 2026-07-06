# Agent Skills Dev Studio

> Local, single-user web portal for authoring Microsoft Agent Skills and chatting with an Azure OpenAI agent over Microsoft Entra ID.

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)
![Vite](https://img.shields.io/badge/Vite-5-646CFF?logo=vite&logoColor=white)
![Azure OpenAI](https://img.shields.io/badge/Azure%20OpenAI-Entra%20ID-0078D4?logo=microsoftazure&logoColor=white)
![Microsoft Agent Framework](https://img.shields.io/badge/Microsoft%20Agent%20Framework-Skills-7A41DC?logo=microsoft&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

<p align="center">
  <img src="docs/panel-overview.png" alt="Agent Skills Dev Studio: projects, skill editor, and test chat in one workspace" width="900">
</p>

**Agent Skills Dev Studio** is a local, single-user web portal for authoring Microsoft Agent Skills and watching how they behave, both on their own and combined, against a live Azure OpenAI agent. Group skills into projects, edit them in Markdown with a live best-practices score, keep a full version history, optionally attach self-contained Python that runs as a tool during the chat, then select several at once and chat with the single agent they form. Every run is graded for adherence, saved as a reusable agent revision, and any two turns can be compared side by side.

Authentication runs entirely through Microsoft Entra ID (managed identity or `az login`). No API keys or connection strings are stored anywhere.

## Highlights

| Capability | What you get |
| --- | --- |
| Skill authoring | Markdown editor with live preview, organized into projects |
| Best-practices score | A 0 to 100 rating with a per-check breakdown that updates as you type |
| Version history | Every save is snapshotted; reload or delete any past version |
| Executable skills | Attach self-contained Python that runs as a sandboxed tool during the chat, localized to your browser |
| Multi-skill agent | Tick several skills and chat with the one agent they combine into |
| Combination analysis | Flags conflicts, contradictions, overlaps, and gaps between selected skills |
| Adherence scoring | Each reply is graded for skill, task, and tool-call adherence by Azure AI Evaluation judges |
| Agent revisions | Every completed run is fingerprinted and saved as a named, reusable revision with rolled-up scores |
| Turn comparison | Mark any two saved turns as baseline and candidate and read the score and tool-call deltas side by side |
| Streaming chat | Token-by-token replies over server-sent events |
| Health check | One click probes the Azure OpenAI endpoint and deployment |

## What's on screen

Three columns, left to right: pick and activate skills, author the selected one, then test the agent they form and grade every run.

```mermaid
flowchart LR
    subgraph LEFT["① Projects · left"]
        direction TB
        P1["Projects &amp; skills tree"]
        P2["Tick skills to<br/>activate the agent"]
        P1 --> P2
    end

    subgraph MID["② Skill editor · center"]
        direction TB
        M1["Name · Description ·<br/>Markdown body"]
        M2["Python code<br/>(optional, runs as a tool)"]
        M3["Best-practices rating 0–100"]
        M4["Version history"]
        M1 --> M2 --> M3 --> M4
    end

    subgraph RIGHT["③ Test chat · right"]
        direction TB
        R1["Active skill chips"]
        R2["Skill compatibility 0–100<br/>conflicts · contradictions · overlaps · gaps"]
        R3["Agent revisions &amp; saved turns"]
        R4["Turn comparison: baseline vs candidate"]
        R5["Streaming conversation"]
        R6["Adherence cards: skill · task · tools"]
        R7["Activity log"]
        R1 --> R2 --> R3 --> R4 --> R5 --> R6 --> R7
    end

    LEFT --> MID --> RIGHT
```

### Projects (left column)

<p align="center">
  <img src="docs/panel-projects.png" alt="Projects column with two projects, skill checkboxes, and drag-and-drop skill creation" width="300">
</p>

The left column is your skill library. Projects group related skills, and each skill has a checkbox that adds it to the live agent plus a name you click to open it in the editor. To create a skill quickly, drop a Markdown file onto a project, and add an optional Python file alongside it for the skill's code. The file name becomes the skill name, which you can rename later. The drop zone lights up as you drag over it.

### Skill editor (center column)

<p align="center">
  <img src="docs/panel-editor.png" alt="Skill editor showing name, description, Markdown body with live preview, Python code, best-practices rating, and version history" width="480">
</p>

The center column authors the selected skill: its name, description, and Markdown body with a live preview beside the source. An optional Python pane carries self-contained code that runs as a tool during the chat. A best-practices rating scores the draft from 0 to 100 and breaks the result into per-check items that update as you type. Every save is snapshotted into version history, so you can reload or delete any past version.

### Test chat (right column)

The right column is the test bench. It combines the active skills into one agent, checks them for conflicts, streams a reply, grades it, and keeps a comparable history. Its four areas are shown below.

#### Skill compatibility

<p align="center">
  <img src="docs/panel-agent-skills.png" alt="Agent skills chips and a skill compatibility report listing conflicts, contradictions, gaps, and overlaps" width="480">
</p>

Active skills appear as chips. With two or more selected, an AI judge scores how well they combine from 0 to 100 and lists every conflict, contradiction, overlap, and gap it finds, all before you send a single message.

#### Agent revisions and saved turns

<p align="center">
  <img src="docs/panel-revisions.png" alt="Agent revisions list with rolled-up scores next to saved turns and baseline or candidate actions" width="480">
</p>

Each completed run is fingerprinted over its skill version snapshots, tool set, and evaluation contract, then saved as an agent revision whose four scores roll up across every turn it has seen. Identical setups fold into the same revision. Turns are stored individually, and you can rename a revision or send any turn to the comparison view.

#### Turn comparison

<p align="center">
  <img src="docs/panel-comparison.png" alt="Two saved turns compared side by side with score and tool-call deltas" width="520">
</p>

Mark any two saved turns as baseline and candidate, even across different revisions, and the compare view reports the deltas for compatibility, tool-call count, and each adherence dimension. Both turns sit side by side, so a wording or selection change is easy to read.

#### Streaming chat, activity log, and adherence

<p align="center">
  <img src="docs/panel-chat.png" alt="Streaming conversation, activity log tracing tool calls, and adherence cards scoring the run" width="480">
</p>

Replies stream token by token over server-sent events. The activity log traces the run step by step, from loading each skill to the individual tool calls and the final composition. When the reply lands, three judges grade it for skill, task, and tool-call adherence.

## Architecture

```mermaid
flowchart LR
    You([You]) --> SPA["React + Vite SPA"]
    SPA -->|/api| API["FastAPI backend"]
    API --> Store[("JSON store<br/>projects · skills · versions<br/>revisions · turns")]

    subgraph Chat["Chat run: skills compared, combined, then graded"]
        direction TB
        AF["Agent Framework<br/>SkillsProvider"]
        S1["Skill A"]
        S2["Skill B"]
        S3["Skill C"]
        AF --> S1
        AF --> S2
        AF --> S3
    end

    API --> Chat
    Chat -->|Entra ID token| AOAI["Azure OpenAI"]
    S1 -->|run_a tool| Exec["Sandboxed Python<br/>(subprocess)"]
    Chat --> Eval["Adherence judges<br/>skill · task · tools"]
    Eval -->|Entra ID token| AOAI
    Eval --> Rev["Agent revision + turn<br/>saved &amp; comparable"]
    Rev --> Store
```

> [!NOTE]
> The chat is where skills come together. Tick several skills and the agent advertises each one, loads them on demand, then compares and combines them in a single conversation: overlaps merge, conflicts surface, and gaps show up.

In production the FastAPI backend serves the compiled SPA and the API together on one origin (port 8000). In development, Vite serves the UI on port 5173 and proxies `/api` to the backend.

## Skills on the fly

Skills are assembled per request, not baked into the agent. Each time you chat, the backend turns the skills you ticked into Microsoft Agent Framework `InlineSkill` objects on the fly (name, description, and Markdown body), hands them to a `SkillsProvider`, and spins up a fresh agent. That makes it cheap to mix and match: change the selection, send a message, and compare how the new combination behaves, all without redeploying or rewriting a single mega-prompt.

## Executable skills

A skill can do more than instruct the model: it can carry self-contained Python that runs as part of the invocation. Add code in the editor's **Python code** pane, and when the skill is active the agent gets a matching `run_<skill>` tool. The model calls it when the skill's instructions ask, the code runs, and its output flows back into the reply.

The code runs in an isolated subprocess with a timeout, a scrubbed environment, and resource limits. This is deliberate, sandboxed execution for a local, single-user studio, not a boundary for untrusted input, so only run code you trust.


> [!WARNING]
> **Experimental, naive isolation — treat skill Python as fully trusted code.** `backend/skill_exec.py` is not a security boundary. Authored code still runs as your OS user and can:
>
> - read and write your local filesystem, including this repository and your `.env`;
> - make unrestricted outbound network calls, including to the Azure Instance Metadata Service (`169.254.169.254`) — so it could mint a **managed-identity token** and reach your Azure resources;
> - import any package in the app's virtual environment (for example `azure-identity`, `httpx`).
>
> The CPU/process/timeout limits and environment scrubbing curb accidental damage, not a malicious skill. Only run skills whose Python you wrote or fully trust, keep this app single-user and unexposed, and run it in a disposable, network-restricted environment such as the provided dev container.

Your browser's timezone and locale travel with each chat message, so a skill can localize what it returns. The code receives a JSON object on stdin with `time_zone`, `locale`, and `user_input`, and prints its result to stdout.

The bundled **localized-time** skill shows the pattern end to end. Its Python reads the browser context and prints the current time formatted for your locale:

```python
import json, sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from babel.dates import format_datetime

data = json.load(sys.stdin)
tz = data.get("time_zone") or "UTC"
locale = (data.get("locale") or "en-US").replace("-", "_")
now = datetime.now(timezone.utc)
print(format_datetime(now, format="full", tzinfo=ZoneInfo(tz), locale=locale))
```

Ask "what time is it?" with that skill active and the agent calls the tool, then answers with a timestamp localized to your browser, for example `Thursday, July 2, 2026, 11:58:01 AM Eastern Daylight Time`.

## Every run is graded, saved, and comparable

Before the agent runs, the active skills are reviewed together and scored for **compatibility** (0–100), with any conflicts, contradictions, overlaps, and gaps called out. After the reply streams in, three judges from the Azure AI Evaluation SDK grade the run:

- **Skill adherence** — did the reply follow the instructions in the active skills?
- **Task adherence** — did it actually do what you asked?
- **Tool-call adherence** — were the expected `run_*` tools invoked with sensible arguments? (Only when an active skill contributes code.)

Each completed run is then fingerprinted over the exact skill version snapshots, the tool set, and the evaluation contract, and saved as an **agent revision**. Runs with an identical setup collapse into the same revision, so its four scores roll up across every turn it has seen. Revisions are named automatically and can be renamed.

Every exchange is also stored as a **turn** — your query, the agent's answer, the tool calls it made, and all four scores. Mark any two turns as **baseline** and **candidate**, even across different revisions, and the compare view reports the deltas for compatibility, tool-call count, and each adherence dimension, with both turns shown side by side.

> [!NOTE]
> The adherence judges authenticate to Azure OpenAI with the same Microsoft Entra ID credential as the chat agent — no API keys. Revisions and turns persist to the local JSON store, so history survives restarts.

## Getting started

There are two ways to run the portal. The dev container path needs the least setup because it ships Python, Node, uv, and the Azure CLI inside the container.

### Option A: Dev container and F5 (recommended)

1. Open the folder in VS Code and choose **Reopen in Container** when prompted. This needs Docker and the Dev Containers extension. On first build the container installs Python, Node, uv, the Azure CLI, and every dependency.
2. Copy the environment template and fill in your Azure OpenAI endpoint and deployment.

   ```bash
   cp .env.example .env
   ```

3. Sign in so `DefaultAzureCredential` has an identity to use.

   ```bash
   az login --use-device-code
   ```

4. Press **F5** and pick **Full Stack: Backend + Frontend**. The backend and the Vite dev server start together.

| Port | What runs there |
| --- | --- |
| 8000 | Portal API and UI |
| 5173 | Vite dev server with hot reload |

> [!TIP]
> The compound launch lives in `.vscode/launch.json`. You can also start the backend or the frontend on its own from the Run and Debug dropdown.

### Option B: Local with uv

Requires Python 3.10+, uv, and Node 18+.

```bash
cp .env.example .env
uv sync
uv run uvicorn backend.main:app --reload
```

Run the frontend with Vite for hot reload during development.

```bash
cd frontend
npm install
npm run dev
```

### Windows shortcut

`start.ps1` wraps both steps. Production mode builds the SPA and serves everything from port 8000; dev mode runs the backend and Vite with hot reload.

```powershell
./start.ps1        # build and serve on http://127.0.0.1:8000
./start.ps1 -Dev   # backend plus Vite hot reload
```

## Configuration

Set these in `.env`, copied from `.env.example`.

| Variable | Required | Purpose |
| --- | --- | --- |
| `AZURE_OPENAI_ENDPOINT` | Yes | Azure OpenAI resource URL |
| `AZURE_OPENAI_CHAT_MODEL` | Yes | Chat deployment name |
| `AZURE_OPENAI_API_VERSION` | No | REST API version (defaults to `2024-10-21`) |

> [!IMPORTANT]
> Keep real values only in `.env`, which is gitignored. The committed `.env.example` holds placeholders. Never put secrets in `.env.example`.

## Authentication

The agent authenticates with Microsoft Entra ID. The backend selects a credential by priority:

1. Service principal (`ClientSecretCredential`) when a client secret, client id, and tenant id are all set.
2. User-assigned managed identity when a managed-identity client id is set.
3. `DefaultAzureCredential` otherwise, which picks up your local `az login`.

Grant whichever identity you use the **Cognitive Services OpenAI User** role on the Azure OpenAI resource. Inside the dev container, `az login` is the usual path; the optional service-principal block in `.env` is read by `.devcontainer/az-login.sh` on container start.

> [!NOTE]
> If a call fails, use the status pill in the top bar to probe the endpoint and deployment.

## Project structure

```text
backend/            FastAPI app
  routes_crud.py    Projects, skills, versions, revisions, and turn-compare endpoints
  routes_chat.py    Streaming chat, adherence evaluation, health
  chat.py           Agent, Azure OpenAI client (Entra ID), skill code tools
  skill_exec.py     Sandboxed subprocess runner for skill Python
  agenteval.py      Pre-run skill-combination compatibility scoring
  adherence.py      Skill, task, and tool-call adherence judges (Azure AI Evaluation)
  validate.py       Best-practices scoring
  store.py          Atomic JSON store: projects, skills, versions, revisions, turns
  data/             Runtime store (gitignored)
frontend/
  src/components/   Tree, Editor, Chat
  src/api.js        Fetch wrappers for the API
.devcontainer/      Container definition and Azure CLI sign-in helpers
start.ps1           Windows launcher
```

## How it works

Skills load through the Agent Framework SkillsProvider instead of being concatenated into one large prompt. Each skill is advertised by name and description, and the agent pulls a full skill body on demand through the `load_skill` tool. When a skill includes Python, the agent also gets a matching `run_<skill>` tool that executes the code in an isolated subprocess and feeds the result back into the reply. Where skills overlap, the agent combines them; where they conflict, it applies the most restrictive rule and points out the conflict. The combination analysis runs the same selection through a scorer that reports conflicts, contradictions, overlaps, and gaps before you start chatting.

After each run the same reply is graded for skill, task, and tool-call adherence, and the whole run — its skill version snapshots, tool calls, and scores — is persisted. Identical setups fold into one agent revision whose scores roll up across turns, and any two saved turns can be compared to see exactly how a wording or selection change moved the numbers.

## License

Released under the [MIT License](LICENSE).
