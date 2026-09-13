"""Pydantic settings loaded from openbundle.yaml + environment."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 4180
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
EXPOSE_HOSTS = {"0.0.0.0", "::", "::0"}


class ProviderConfig(BaseModel):
    api_key: str = ""
    base_url: str = ""


class ExtractConfig(BaseModel):
    every_n_turns: int = 3
    min_interval_seconds: float = 15
    max_per_minute: int = 4
    skip_if_user_tokens_below: int = 50


class CacheLayerConfig(BaseModel):
    enabled: bool = True
    semantic: bool = False
    semantic_threshold: float = 0.95
    path: str = ""


class MemoryLayerConfig(BaseModel):
    enabled: bool = False
    user_id: str = "local"
    adapter: str = "summary"
    window: int = 12
    extract: ExtractConfig = Field(default_factory=ExtractConfig)


class CompressLayerConfig(BaseModel):
    enabled: bool = False
    rate: float = 0.5
    skip_cache_control: bool = True
    adapter: str = "llmlingua2"


class RoutingLayerConfig(BaseModel):
    enabled: bool = False
    adapter: str = "prefix_router"


class GuardrailsLayerConfig(BaseModel):
    enabled: bool = False
    adapter: str = "input_guard"


class StructuredLayerConfig(BaseModel):
    enabled: bool = False
    adapter: str = "json_schema"


class EvalLayerConfig(BaseModel):
    enabled: bool = False
    adapter: str = "sample_eval"


class LayersConfig(BaseModel):
    cache: CacheLayerConfig = Field(default_factory=CacheLayerConfig)
    memory: MemoryLayerConfig = Field(default_factory=MemoryLayerConfig)
    compress: CompressLayerConfig = Field(default_factory=CompressLayerConfig)
    routing: RoutingLayerConfig = Field(default_factory=RoutingLayerConfig)
    guardrails: GuardrailsLayerConfig = Field(default_factory=GuardrailsLayerConfig)
    structured: StructuredLayerConfig = Field(default_factory=StructuredLayerConfig)
    eval: EvalLayerConfig = Field(default_factory=EvalLayerConfig)


class BundleConfig(BaseModel):
    cache: str = "sqlite_exact"
    memory: str = "none"
    compress: str = "none"
    routing: str = "none"
    guardrails: str = "none"
    structured: str = "none"
    eval: str = "none"


class ProvidersConfig(BaseModel):
    anthropic: ProviderConfig = Field(
        default_factory=lambda: ProviderConfig(
            api_key="env:ANTHROPIC_API_KEY",
            base_url="https://api.anthropic.com",
        )
    )
    openai: ProviderConfig = Field(
        default_factory=lambda: ProviderConfig(
            api_key="env:OPENAI_API_KEY",
            base_url="https://api.openai.com/v1",
        )
    )


class Settings(BaseModel):
    listen: str = f"{DEFAULT_HOST}:{DEFAULT_PORT}"
    enabled: bool = True
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    bundle: BundleConfig = Field(default_factory=BundleConfig)
    layers: LayersConfig = Field(default_factory=LayersConfig)
    passthrough: bool = False
    session_dir: str = ""
    config_path: str = ""

    @property
    def host(self) -> str:
        host, _, _port = self.listen.rpartition(":")
        return host or DEFAULT_HOST

    @property
    def port(self) -> int:
        _host, _, port = self.listen.rpartition(":")
        try:
            return int(port)
        except ValueError:
            return DEFAULT_PORT

    def session_path(self) -> Path:
        if self.session_dir:
            return Path(self.session_dir).expanduser()
        return Path.home() / ".openbundle" / "sessions"

    def cache_path(self) -> Path:
        if self.layers.cache.path:
            return Path(self.layers.cache.path).expanduser()
        return Path.home() / ".openbundle" / "cache.sqlite"


def state_dir() -> Path:
    return Path.home() / ".openbundle"


def install_record_path() -> Path:
    return state_dir() / "install-record.yaml"


def overlay_path() -> Path:
    return state_dir() / "overlay.yaml"


def resolve_secret(value: str) -> str:
    if value.startswith("env:"):
        return os.environ.get(value[4:], "")
    if value.startswith("${") and value.endswith("}"):
        return os.environ.get(value[2:-1], "")
    return value


def default_config_candidates() -> list[Path]:
    env = os.environ.get("OPENBUNDLE_CONFIG")
    paths = []
    if env:
        paths.append(Path(env))
    paths.extend(
        [
            Path.cwd() / "openbundle.yaml",
            Path.home() / ".openbundle" / "openbundle.yaml",
        ]
    )
    return paths


def load_settings(path: Path | None = None) -> Settings:
    data: dict[str, Any] = {}
    used = ""
    if path:
        data = _read_yaml(path)
        used = str(path)
    else:
        for candidate in default_config_candidates():
            if candidate.is_file():
                data = _read_yaml(candidate)
                used = str(candidate)
                break
    settings = Settings.model_validate(data or {})
    settings.config_path = used
    return settings


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"Config {path} must be a mapping")
    return loaded


def expose_allowed() -> bool:
    return os.environ.get("OPENBUNDLE_EXPOSE", "").strip() in {"1", "true", "TRUE", "yes"}


def _env_overlay() -> bool | None:
    raw = os.environ.get("OPENBUNDLE_ENABLED", "").strip().lower()
    if raw in {"0", "false", "off", "no"}:
        return False
    if raw in {"1", "true", "on", "yes"}:
        return True
    return None


def find_config_file() -> Path | None:
    for candidate in default_config_candidates():
        if candidate.is_file():
            return candidate
    return None


def overlay_enabled(settings: Settings | None = None) -> bool:
    """Env > --passthrough > ~/.openbundle/overlay.yaml > default on."""
    forced = _env_overlay()
    if forced is not None:
        return forced
    if settings is not None and settings.passthrough:
        return False
    path = overlay_path()
    if path.is_file():
        try:
            data = _read_yaml(path)
        except Exception:
            data = {}
        if "enabled" in data:
            return bool(data["enabled"])
    if settings is not None:
        return bool(settings.enabled)
    return True


def env_overlay_set() -> bool:
    return _env_overlay() is not None


def write_overlay_enabled(enabled: bool) -> Path:
    path = overlay_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, Any] = {}
    if path.is_file():
        try:
            existing = _read_yaml(path)
        except Exception:
            existing = {}
    existing["enabled"] = enabled
    write_config_doc(path, existing)
    return path


def read_config_doc(path: Path) -> dict[str, Any]:
    return _read_yaml(path)


def write_config_doc(path: Path, data: dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def set_enabled(path: Path, enabled: bool) -> None:
    data = read_config_doc(path)
    data["enabled"] = enabled
    write_config_doc(path, data)


def validate_bind(host: str, *, expose: bool = False) -> None:
    normalized = host.strip().lower()
    if normalized in EXPOSE_HOSTS or normalized in {"*", "[::]"}:
        if not (expose or expose_allowed()):
            raise BindError(
                f"Refusing to bind {host}: v1 listens on 127.0.0.1 only. "
                "Re-run with --expose (or OPENBUNDLE_EXPOSE=1) if you intend to "
                "make provider keys on this box reachable on the LAN."
            )


class BindError(SystemExit):
    """Raised when the proxy would bind a non-loopback address without --expose."""
