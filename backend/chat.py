"""Agent construction helpers for the Azure OpenAI chat agent.

Builds Microsoft Agent Framework agents backed by Azure OpenAI using Microsoft
Entra ID credentials (no API key or connection string). The credential is
selected by priority: a service principal client secret when configured, then a
user-assigned managed identity, then ``DefaultAzureCredential``.

Selected skill prompts are loaded with the framework's built-in Agent Skills
system (``SkillsProvider``, progressive disclosure) rather than concatenated
into one large prompt: each skill is advertised by name and description, and the
agent loads the full skill body on demand via the ``load_skill`` tool.
"""

import asyncio
import logging
import re

from agent_framework import (
    Agent,
    InlineSkill,
    SkillFrontmatter,
    SkillsProvider,
)
from agent_framework.openai import OpenAIChatClient
from azure.identity.aio import (
    ClientSecretCredential,
    DefaultAzureCredential,
    ManagedIdentityCredential,
)

from backend import config, skill_exec

logger = logging.getLogger("agent_skill_portal.chat")

_AGENT_INSTRUCTIONS = (
    "You are an assistant assembled from the skills advertised to you. "
    "Before answering, use the load_skill tool to load every advertised skill, "
    "then follow all of them at the same time. Where skills overlap, combine "
    "them. Where skills conflict, apply the most restrictive rule and briefly "
    "tell the user about the conflict. Use read_skill_resource for any resources "
    "a skill references. "
    "When an advertised skill provides an executable tool (named run_...), call "
    "that tool to perform the skill's action and use its output in your answer."
)


def _build_credential(settings: config.Settings):
    """Select an async Azure credential by priority.

    The first applicable mode is used:

    1. Service principal (``ClientSecretCredential``) when a client secret,
       client id, and tenant id are all available.
    2. User-assigned managed identity (``ManagedIdentityCredential``) when a
       managed-identity client id is available.
    3. ``DefaultAzureCredential`` (for example, the local ``az login``).

    Args:
        settings: The loaded configuration.

    Returns:
        An async token credential from ``azure.identity.aio``.
    """
    if (
        settings.sp_client_secret
        and settings.sp_client_id
        and settings.sp_tenant_id
    ):
        logger.info(
            "Authenticating with service principal (client id %s).",
            settings.sp_client_id,
        )
        return ClientSecretCredential(
            tenant_id=settings.sp_tenant_id,
            client_id=settings.sp_client_id,
            client_secret=settings.sp_client_secret,
        )
    if settings.mi_client_id:
        logger.info(
            "Authenticating with managed identity (client id %s).",
            settings.mi_client_id,
        )
        return ManagedIdentityCredential(client_id=settings.mi_client_id)
    logger.info("Authenticating with DefaultAzureCredential.")
    return DefaultAzureCredential()


def _build_client(settings: config.Settings) -> OpenAIChatClient:
    """Create an Azure OpenAI chat client using the selected Entra ID credential."""
    return OpenAIChatClient(
        azure_endpoint=settings.endpoint,
        model=settings.chat_model,
        api_version=settings.api_version,
        credential=_build_credential(settings),
    )


def make_agent(instructions: str, name: str = "Skill Agent") -> Agent:
    """Build an agent with the given instructions and a managed-identity client.

    Args:
        instructions: The system instructions for the agent.
        name: A display name (truncated to 64 characters).

    Returns:
        Agent: A Microsoft Agent Framework agent connected to Azure OpenAI.
    """
    return Agent(
        client=_build_client(config.load_settings()),
        name=name[:64] or "Skill Agent",
        instructions=instructions,
    )


def _skill_name(raw: str, index: int) -> str:
    """Coerce a prompt name into a spec-valid skill name (kebab-case, <=64)."""
    slug = re.sub(r"[^a-z0-9]+", "-", (raw or "").lower())
    slug = re.sub(r"-{2,}", "-", slug).strip("-")[:64].strip("-")
    return slug or f"skill-{index + 1}"


def _to_skills(prompts: list) -> list[InlineSkill]:
    """Turn stored prompts into framework ``InlineSkill`` objects.

    Names are slugged to satisfy the Agent Skills spec and de-duplicated so no
    skill is silently dropped; descriptions and bodies fall back to safe,
    non-empty defaults.
    """
    skills: list[InlineSkill] = []
    used: set[str] = set()
    for index, prompt in enumerate(prompts):
        name = _skill_name(getattr(prompt, "name", ""), index)
        base, suffix = name, 2
        while name in used:
            name = f"{base[:60]}-{suffix}"
            suffix += 1
        used.add(name)

        description = (getattr(prompt, "description", "") or "").strip()[
            :1024
        ] or f"Skill {name}."
        instructions = (
            getattr(prompt, "content", "") or ""
        ).strip() or description

        skills.append(
            InlineSkill(
                frontmatter=SkillFrontmatter(
                    name=name, description=description
                ),
                instructions=instructions,
            )
        )
    return skills


def _tool_name(skill_name: str) -> str:
    """Framework tool name for a skill's executor (unique, identifier-safe)."""
    return "run_" + re.sub(r"[^a-z0-9]+", "_", skill_name.lower()).strip("_")


def _make_skill_tool(code: str, skill_name: str, description: str, ctx: dict):
    """Build a sync callable tool that executes one skill's Python."""

    def run_skill(user_input: str = "") -> str:
        return skill_exec.run(code, {**ctx, "user_input": user_input})

    run_skill.__name__ = _tool_name(skill_name)
    run_skill.__doc__ = (
        f"Execute the '{skill_name}' skill's code and return its output. "
        f"{description}".strip()
    )
    return run_skill


def build_agent(
    prompts,
    time_zone: str | None = None,
    locale: str | None = None,
) -> Agent:
    """Create an agent that loads and follows every supplied skill.

    Skills are exposed through the framework's :class:`SkillsProvider` so they
    are advertised (name + description) and loaded on demand instead of being
    concatenated into a single large system prompt. Each skill that carries
    executable ``code`` also contributes one uniquely named ``run_*`` tool that
    runs that skill's Python; browser localization (``time_zone``/``locale``)
    is threaded into every such tool's execution context.

    Args:
        prompts: A single prompt object or a list of them, each exposing
            ``name``, ``description``, ``content``, and optionally ``code``.
        time_zone: The caller's IANA time zone, passed to skill executors.
        locale: The caller's BCP 47 locale, passed to skill executors.

    Returns:
        Agent: A Microsoft Agent Framework agent connected to Azure OpenAI via
        managed identity, with the selected skills and their execution tools
        attached.
    """
    prompt_list = prompts if isinstance(prompts, list) else [prompts]
    skills = _to_skills(prompt_list)
    names = ", ".join(s.frontmatter.name for s in skills) or "Skill Agent"
    ctx = {"time_zone": time_zone, "locale": locale}
    tools = [
        _make_skill_tool(
            p.code, s.frontmatter.name, s.frontmatter.description, ctx
        )
        for p, s in zip(prompt_list, skills)
        if (getattr(p, "code", "") or "").strip()
    ]
    return Agent(
        client=_build_client(config.load_settings()),
        name=f"Skill Agent ({names})"[:64],
        instructions=_AGENT_INSTRUCTIONS,
        context_providers=[SkillsProvider(skills)],
        tools=tools,
    )


async def check_health() -> dict:
    """Probe the Azure OpenAI endpoint and chat model with managed identity.

    Sends a minimal request through the same managed-identity client the chat
    agent uses, confirming the endpoint, deployment, and credential are all
    reachable. No API key or connection string is involved.

    Returns:
        dict: ``status`` ("healthy", "unhealthy", or "unconfigured"),
        ``detail`` (human-readable), and the ``endpoint`` and ``model`` that
        were probed (empty strings when configuration is missing).
    """
    try:
        settings = config.load_settings()
    except RuntimeError as exc:
        return {
            "status": "unconfigured",
            "detail": str(exc),
            "endpoint": "",
            "model": "",
        }

    async def _probe() -> None:
        # Mirror the chat path (streaming) so the probe succeeds as soon as the
        # model streams anything back, instead of waiting for a full completion.
        agent = make_agent("Reply with the single word: ok.", "Health Probe")
        async for chunk in agent.run("ping", stream=True):
            if getattr(chunk, "text", None):
                return

    try:
        await asyncio.wait_for(_probe(), timeout=30)
    except asyncio.TimeoutError:
        logger.warning("Azure OpenAI health probe timed out")
        return {
            "status": "unhealthy",
            "detail": "The endpoint did not respond within 30 seconds.",
            "endpoint": settings.endpoint,
            "model": settings.chat_model,
        }
    except Exception as exc:
        logger.warning("Azure OpenAI health probe failed: %s", exc)
        detail = f"{type(exc).__name__}: {exc}".strip()
        return {
            "status": "unhealthy",
            "detail": detail[:300] or "The endpoint did not respond.",
            "endpoint": settings.endpoint,
            "model": settings.chat_model,
        }

    return {
        "status": "healthy",
        "detail": f"Model '{settings.chat_model}' responded.",
        "endpoint": settings.endpoint,
        "model": settings.chat_model,
    }
