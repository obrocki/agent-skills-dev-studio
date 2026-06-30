"""Application configuration.

Loads Azure OpenAI connection settings and credential-selection inputs from the
environment. Authentication uses Microsoft Entra ID (no API key or connection
string): a service principal client secret when configured, then a user-assigned
managed identity, then ``DefaultAzureCredential``.
"""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    """Validated Azure OpenAI settings used by the portal.

    Attributes:
        endpoint: Azure OpenAI resource endpoint URL.
        chat_model: Deployment name of the chat model.
        api_version: Azure OpenAI REST API version.
        sp_tenant_id: Service principal tenant (Entra ID directory) id.
        sp_client_id: Service principal (application) client id.
        sp_client_secret: Service principal client secret.
        mi_client_id: User-assigned managed identity client id.
    """

    endpoint: str
    chat_model: str
    api_version: str
    sp_tenant_id: str | None
    sp_client_id: str | None
    sp_client_secret: str | None
    mi_client_id: str | None


def load_settings() -> Settings:
    """Read and validate required environment variables.

    Returns:
        Settings: The validated configuration.

    Raises:
        RuntimeError: If a required variable is missing or empty.
    """
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
    chat_model = os.getenv("AZURE_OPENAI_CHAT_MODEL", "").strip()
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21").strip()

    # Service principal (client secret) credentials. The tenant falls back to
    # the managed-identity tenant, since the SP and MI share the directory.
    sp_client_id = os.getenv("SP_AZURE_CLIENT_ID", "").strip() or None
    sp_client_secret = os.getenv("SP_AZURE_CLIENT_SECRET", "").strip() or None
    sp_tenant_id = (
        os.getenv("SP_AZURE_TENANT_ID", "").strip()
        or os.getenv("MI_AZURE_TENANT_ID", "").strip()
        or os.getenv("AZURE_TENANT_ID", "").strip()
        or None
    )

    # User-assigned managed identity (legacy AZURE_CLIENT_ID still accepted).
    mi_client_id = (
        os.getenv("MI_AZURE_CLIENT_ID", "").strip()
        or os.getenv("AZURE_CLIENT_ID", "").strip()
        or None
    )

    missing = [
        name
        for name, value in (
            ("AZURE_OPENAI_ENDPOINT", endpoint),
            ("AZURE_OPENAI_CHAT_MODEL", chat_model),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(
            "Missing required environment variables: "
            + ", ".join(missing)
            + ". Copy .env.example to .env and set them."
        )

    return Settings(
        endpoint=endpoint,
        chat_model=chat_model,
        api_version=api_version,
        sp_tenant_id=sp_tenant_id,
        sp_client_id=sp_client_id,
        sp_client_secret=sp_client_secret,
        mi_client_id=mi_client_id,
    )
