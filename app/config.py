"""Central application configuration via pydantic-settings."""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM
    openrouter_api_key: str = ""
    openrouter_model: str = "openai/gpt-4o"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_max_concurrent_requests: int = 10

    # Zotero
    zotero_api_key: str = ""
    zotero_library_id: str = ""
    zotero_library_type: str = "user"
    zotero_max_concurrent_requests: int = 4

    # Database
    database_url: str = "sqlite:///./lit_anal.db"

    # PDF storage
    pdf_download_dir: Path = Path("./data/pdfs")
    extraction_dir: Path = Path("./data/extractions")
    extraction_write_markdown: bool = True
    extraction_write_html: bool = True
    extraction_write_json: bool = True
    extraction_write_doctags: bool = True

    # Langfuse (optional – empty keys disable tracing)
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    @property
    def langfuse_enabled(self) -> bool:
        return bool(self.langfuse_public_key and self.langfuse_secret_key)


# Module-level singleton – import this everywhere
settings = Settings()
