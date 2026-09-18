"""openbundle CLI: init / on / off / check / config / serve / report / doctor."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

import typer
import uvicorn
import yaml
from fastapi.testclient import TestClient

from openbundle import __version__
from openbundle.banner import print_banner
from openbundle.config import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    BindError,
    env_overlay_set,
    find_config_file,
    load_settings,
    overlay_enabled,
    read_config_doc,
    validate_bind,
    write_config_doc,
    write_overlay_enabled,
)
from openbundle.init.install import (
    collect_uninstall_targets,
    pip_uninstall_packages,
    record_config_file,
    remove_paths,
)
from openbundle.init.scan import installed_extras, scan_env
from openbundle.kb.credits import write_credits
from openbundle.kb.display import (
    active_from_doc,
    apply_bundle_to_doc,
    format_config_view,
    format_init_summary,
)
from openbundle.kb.catalog import WRAP_CATEGORIES, credit_line, get_tool, incompatibility
from openbundle.kb.select import select
from openbundle.kb.status import format_status
from openbundle.metrics.smoke import smoke_check_compress
from openbundle.pipeline.jobs import HOSTED_JOB_IDS
from openbundle.metrics.cost import lookup_model, stale_rows
from openbundle.metrics.report import print_report
from openbundle.metrics.session import SessionLog
from openbundle.progress import Pulse
from openbundle.proxy.app import create_app
from openbundle.update import check_update, pip_upgrade

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="OpenBundle optimization overlay.",
)
config_app = typer.Typer(help="Show or swap overlay tools.", invoke_without_command=True)


def _banner(no_banner: bool, compact: bool = False) -> None:
    print_banner(no_banner=no_banner, compact=compact)


def _write_config(output: Path, choice) -> None:
    live = choice.live
    jobs = {job_id: bool(choice.jobs.get(job_id) not in (None, "", "none")) for job_id in HOSTED_JOB_IDS}
    if choice.local_inference:
        from openbundle.pipeline.jobs import SELF_HOSTED_JOB_IDS

        for job_id in SELF_HOSTED_JOB_IDS:
            jobs[job_id] = True
    bundle = {job_id: choice.jobs.get(job_id, "none") for job_id in HOSTED_JOB_IDS}
    bundle["memory"] = "none"
    bundle["batch"] = "none"
    doc = {
        "listen": f"{DEFAULT_HOST}:{DEFAULT_PORT}",
        "with_lynx": bool(choice.with_lynx),
        "local_obs": bool(choice.local_obs),
        "providers": {
            "anthropic": {
                "api_key": "env:ANTHROPIC_API_KEY",
                "base_url": "https://api.anthropic.com",
            },
            "openai": {
                "api_key": "env:OPENAI_API_KEY",
                "base_url": "https://api.openai.com/v1",
            },
        },
        "bundle": bundle,
        "jobs": jobs,
        "layers": {
            "cache": {"enabled": jobs.get("exact_hash", True), "semantic": False},
            "compress": {
                "enabled": jobs.get("compress", False),
                "rate": 0.5,
                "skip_cache_control": True,
                "adapter": "llmlingua2",
            },
            "structured": {"enabled": jobs.get("structured", False), "adapter": "instructor"},
            "nemo_rails": {
                "enabled": jobs.get("nemo_rails", False),
                "adapter": "nemo_guardrails",
                "llm_check": bool(jobs.get("nemo_rails", False)),
            },
            "memory": {"enabled": False, "adapter": "none"},
            "batch": {"enabled": False, "adapter": "none"},
        },
    }
    output.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    record_config_file(output)


def _env_conflict_note() -> None:
    if env_overlay_set():
        typer.echo(
            f"OPENBUNDLE_ENABLED={os.environ.get('OPENBUNDLE_ENABLED')} is set and "
            "overrides overlay.yaml until you unset it."
        )


def _credited_bundle(doc: dict) -> str:
    active = active_from_doc(doc)
    parts = []
    for category in WRAP_CATEGORIES:
        tool_id = active.get(category) or "none"
        if tool_id != "none":
            parts.append(credit_line(tool_id))
    return ", ".join(parts) if parts else "passthrough"


@app.command("on")
def overlay_on() -> None:
    """Turn the overlay on. Same attach URL; repo is not touched."""
    write_overlay_enabled(True)
    typer.echo("Overlay on. Layers run on http://127.0.0.1:4180.")
    typer.echo("Repo and source were not touched. Same attach URL still works.")
    _env_conflict_note()


@app.command("off")
def overlay_off() -> None:
    """Turn the overlay off. Same attach URL; requests passthrough."""
    write_overlay_enabled(False)
    typer.echo("Overlay off. Same attach URL; requests passthrough.")
    typer.echo("Repo and source were not touched.")
    _env_conflict_note()


@app.command("check")
def check(
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    no_banner: bool = typer.Option(False, "--no-banner"),
) -> None:
    """Re-select jobs from the current environment and rewrite the overlay."""
    _banner(no_banner)
    path = config or find_config_file()
    if path is None:
        typer.echo("No openbundle.yaml found. Run `openbundle init` first.", err=True)
        raise typer.Exit(code=2)
    extras = installed_extras()
    scan = scan_env()
    choice = select(scan, extras, allow_lossy=True)
    if choice.jobs.get("compress") == "llmlingua2" and not smoke_check_compress():
        choice.jobs["compress"] = "none"
        choice.live["compress"] = False
        typer.echo("compress skipped: smoke-check failed on local samples.")
    _write_config(path, choice)
    write_credits(Path.cwd() / "CREDITS.md")
    typer.echo(format_init_summary(choice))
    typer.echo("Selection applied. Repo and source were not touched.")


@app.command()
def init(
    output: Path = typer.Option(Path("openbundle.yaml"), "--output", "-o"),
    core_only: bool = typer.Option(False, "--core-only", help="Exact-hash only."),
    with_lynx: bool = typer.Option(False, "--with-lynx", help="Enable Lynx-8B faithfulness if local inference exists."),
    local_obs: bool = typer.Option(False, "--local-obs", help="Point obs SDKs at localhost instead of vendor hosted tiers."),
    no_banner: bool = typer.Option(False, "--no-banner"),
) -> None:
    """Resolve 23 jobs, write the overlay, start Tier B warming, regenerate CREDITS.md."""
    _banner(no_banner)
    with Pulse("Checking compatibility", show_logo=not no_banner):
        scan = scan_env()
        extras = [] if core_only else installed_extras()
    with Pulse("Selecting tools", show_logo=False):
        choice = select(
            scan,
            extras,
            core_only=core_only,
            allow_lossy=True,
            with_lynx=with_lynx,
            local_obs=local_obs,
        )
    with Pulse("Writing config", show_logo=False):
        _write_config(output, choice)
        write_credits(Path.cwd() / "CREDITS.md")
        write_overlay_enabled(True)
    typer.echo(format_init_summary(choice))
    typer.echo("")
    if not local_obs:
        typer.echo(
            "Observability SDKs default to vendor hosted free tiers. "
            "Traces leave this machine. Pass --local-obs to keep them here."
        )
        typer.echo("")
    typer.echo(
        "Input scanners fail-open so a broken extra never blocks you. "
        "If one errors, `openbundle status` prints a DEGRADED banner, not a quiet live."
    )
    typer.echo(
        "NeMo rails reuse your provider: extra tokens and latency when they fire "
        "(nemo_rail_tokens on status). GPTCache and Semantic Router do not share "
        "an embedding download unless a joint load test exists."
    )
    typer.echo("")
    if not scan.anthropic_key and not scan.openai_key:
        typer.echo("No ANTHROPIC_API_KEY or OPENAI_API_KEY in the environment.")
    typer.echo("Attach your client:")
    typer.echo(f"  export ANTHROPIC_BASE_URL=http://{DEFAULT_HOST}:{DEFAULT_PORT}")
    typer.echo(f"  # or OpenAI: base_url=http://{DEFAULT_HOST}:{DEFAULT_PORT}/v1")
    typer.echo("")
    typer.echo("Then:  openbundle serve")
    typer.echo("Live number: openbundle status")
    typer.echo("Toggle: openbundle on | openbundle off")


@app.command()
def status(
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    no_banner: bool = typer.Option(False, "--no-banner"),
) -> None:
    """Per-stage live | warming | degraded | advisory | off. DEGRADED is a banner, not a table cell."""
    _banner(no_banner, compact=True)
    settings = load_settings(config)
    pipeline = create_app(settings).state.pipeline
    typer.echo(format_status(pipeline.registry, overlay_on=overlay_enabled(settings)))


@config_app.callback(invoke_without_command=True)
def config_root(ctx: typer.Context, no_banner: bool = typer.Option(False, "--no-banner")) -> None:
    if ctx.invoked_subcommand is not None:
        return
    _banner(no_banner, compact=True)
    path = find_config_file()
    extras = installed_extras()
    if path is None:
        scan = scan_env()
        choice = select(scan, extras)
        active = dict(choice.jobs)
    else:
        active = active_from_doc(read_config_doc(path))
    typer.echo(format_config_view(extras, active=active))


@config_app.command("set")
def config_set(
    category: str = typer.Argument(help="cache | memory | compress | routing | …"),
    tool: str = typer.Argument(help="Tool id, or off / none"),
    no_banner: bool = typer.Option(False, "--no-banner"),
) -> None:
    """Swap one wrap category to a wired tool, or off."""
    _banner(no_banner, compact=True)
    alias = {
        "compression": "compress",
        "caching": "exact_hash",
        "cache": "exact_hash",
        "hygiene": "history",
    }
    category = alias.get(category, category)
    if category in {"batch", "memory"}:
        typer.echo(
            f"{category} is advisory — not on the live path.",
            err=True,
        )
        raise typer.Exit(code=2)
    if category not in WRAP_CATEGORIES:
        typer.echo(
            f"Unknown category {category}. Use {', '.join(WRAP_CATEGORIES)}.",
            err=True,
        )
        raise typer.Exit(code=2)
    tool_id = "none" if tool in {"off", "none", "disabled"} else tool
    path = find_config_file()
    if path is None:
        typer.echo("No openbundle.yaml found. Run `openbundle init` first.", err=True)
        raise typer.Exit(code=2)
    doc = read_config_doc(path)
    if tool_id != "none":
        catalog_tool = get_tool(tool_id)
        if catalog_tool is None:
            typer.echo(f"Unknown tool {tool_id}.", err=True)
            raise typer.Exit(code=2)
        extras = set(installed_extras())
        active = active_from_doc(doc)
        others = [active[c] for c in WRAP_CATEGORIES if c != category and active.get(c) not in (None, "", "none")]
        why = incompatibility(catalog_tool, extras, others)
        if why:
            typer.echo(f"Cannot set {category} to {tool_id}: {why}", err=True)
            raise typer.Exit(code=2)
    apply_bundle_to_doc(doc, category, tool_id)
    write_config_doc(path, doc)
    record_config_file(path)
    if tool_id == "none":
        typer.echo(f"{category} off. Repo and source were not touched.")
    else:
        typer.echo(f"{category} → {credit_line(tool_id)}")
        typer.echo("Repo and source were not touched.")


app.add_typer(config_app, name="config")


@app.command()
def serve(
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    host: Optional[str] = typer.Option(None, "--host"),
    port: Optional[int] = typer.Option(None, "--port"),
    expose: bool = typer.Option(False, "--expose", help="Allow binding 0.0.0.0 (LAN)."),
    passthrough: bool = typer.Option(False, "--passthrough", help="Disable all optimization layers."),
    no_banner: bool = typer.Option(False, "--no-banner"),
) -> None:
    """Run the localhost proxy."""
    _banner(no_banner)
    if config:
        os.environ["OPENBUNDLE_CONFIG"] = str(config)
    settings = load_settings(config)
    if passthrough:
        settings.passthrough = True
        settings.layers.cache.enabled = False
        settings.jobs = {job_id: False for job_id in HOSTED_JOB_IDS}
    bind_host = host or settings.host
    bind_port = port or settings.port
    try:
        validate_bind(bind_host, expose=expose)
    except BindError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    if expose:
        typer.echo(
            "WARNING: --expose binds beyond loopback. Provider keys on this box "
            "are reachable on the LAN.",
            err=True,
        )
    on = overlay_enabled(settings)
    typer.echo(f"OpenBundle v{__version__} listening on http://{bind_host}:{bind_port}")
    typer.echo(f"overlay: {'on' if on else 'off'}")
    if settings.config_path:
        doc = read_config_doc(Path(settings.config_path))
        typer.echo(f"tools: {_credited_bundle(doc)}")
    if settings.passthrough or not on:
        typer.echo("passthrough: layers off")

    def factory() -> object:
        return create_app(settings)

    uvicorn.run(
        factory,
        factory=True,
        host=bind_host,
        port=bind_port,
        log_level="warning",
        access_log=False,
    )


@app.command()
def report(
    session: Optional[Path] = typer.Option(None, "--session"),
    no_banner: bool = typer.Option(False, "--no-banner"),
) -> None:
    """Print a before/after table for the latest session."""
    _banner(no_banner, compact=True)
    settings = load_settings()
    path = session or SessionLog.latest(settings.session_path())
    if path is None or not path.is_file():
        typer.echo("No session log found. Run traffic through `openbundle serve` first.")
        raise typer.Exit(code=1)
    print_report(path)


@app.command()
def doctor(
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    no_banner: bool = typer.Option(False, "--no-banner"),
) -> None:
    """Check extras, keys, /health, and stale pricing rows."""
    _banner(no_banner)
    settings = load_settings(config)
    extras = installed_extras()
    scan = scan_env()
    ok = True
    typer.echo(f"config: {settings.config_path or '(defaults)'}")
    typer.echo(f"listen: {settings.listen}  (loopback-only unless --expose)")
    typer.echo(f"overlay: {'on' if overlay_enabled(settings) else 'off'}")
    if settings.config_path:
        doc = read_config_doc(Path(settings.config_path))
        typer.echo(f"tools: {_credited_bundle(doc)}")
    typer.echo(f"extras: {', '.join(extras) if extras else '(none - light core)'}")
    typer.echo(f"ANTHROPIC_API_KEY: {'yes' if scan.anthropic_key else 'missing'}")
    typer.echo(f"OPENAI_API_KEY:    {'yes' if scan.openai_key else 'missing'}")
    if not scan.anthropic_key and not scan.openai_key:
        ok = False
    app_obj = create_app(settings)
    with TestClient(app_obj) as client:
        health = client.get("/health")
    typer.echo(f"health: {health.status_code} {health.json()}")
    stale = stale_rows()
    if stale:
        ok = False
        typer.echo("pricing stale (>30 days):")
        for row in stale:
            typer.echo(f"  {row.model} last_verified={row.last_verified} source={row.source}")
    else:
        sample = lookup_model("claude-sonnet-4-6")
        if sample:
            typer.echo(f"pricing: claude-sonnet-4-6 as of {sample.last_verified}")
    if not ok:
        raise typer.Exit(code=1)
    typer.echo("doctor: ok")


@app.command()
def uninstall(
    yes: bool = typer.Option(False, "--yes", "-y", help="Do not prompt."),
    keep_package: bool = typer.Option(
        False, "--keep-package", help="Leave the openbundle pip package installed."
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show pip output instead of the progress bar."),
    no_banner: bool = typer.Option(False, "--no-banner"),
) -> None:
    """Remove configs, cache, sessions, extras OpenBundle installed, and the package."""
    _banner(no_banner)
    targets = collect_uninstall_targets()
    typer.echo("This removes OpenBundle from this device. It does not edit your repo.")
    typer.echo("")
    typer.echo("Will delete:")
    if targets["config_files"]:
        for path in targets["config_files"]:
            typer.echo(f"  config  {path}")
    else:
        typer.echo("  config  (none found)")
    typer.echo(f"  state   {targets['state_dir']}  (cache, sessions, install record)")
    pkgs = list(targets["pip_packages"])
    if pkgs:
        typer.echo(f"  extras  pip uninstall {' '.join(pkgs)}")
    if not keep_package:
        typer.echo("  self    pip uninstall openbundle")
    typer.echo("")
    typer.echo("Then unset ANTHROPIC_BASE_URL / OpenAI base_url if you pointed them here.")
    typer.echo("")

    if yes:
        approved = True
    elif sys.stdin.isatty():
        approved = typer.confirm("Remove everything listed above?", default=False)
    else:
        typer.echo("No TTY: pass --yes to uninstall.")
        raise typer.Exit(code=2)

    if not approved:
        typer.echo("Aborted.")
        raise typer.Exit(code=1)

    removed = remove_paths(targets["config_files"])
    state = Path(targets["state_dir"])
    if state.exists():
        remove_paths([str(state)])
        removed.append(str(state))
    for path in removed:
        typer.echo(f"removed {path}")

    to_uninstall = list(pkgs)
    if not keep_package:
        to_uninstall.append("openbundle")
    if to_uninstall:
        code = pip_uninstall_packages(to_uninstall, quiet=not verbose, show_logo=not no_banner)
        if code != 0:
            typer.echo("pip uninstall reported an error; check the packages above.", err=True)

    typer.echo("")
    typer.echo("Done. If a client still points at http://127.0.0.1:4180, undo that:")
    typer.echo("  unset ANTHROPIC_BASE_URL")
    typer.echo("  # and restore any OpenAI base_url override")


@app.command()
def update(
    check: bool = typer.Option(False, "--check", help="Only report; do not install."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Upgrade without prompting."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show pip output instead of the progress bar."),
    no_banner: bool = typer.Option(False, "--no-banner"),
) -> None:
    """Check PyPI for a newer OpenBundle and install it."""
    _banner(no_banner, compact=True)
    status = check_update()
    typer.echo(f"installed: {status.current}")
    if status.latest:
        typer.echo(f"pypi:      {status.latest}")
    else:
        typer.echo("pypi:      (not published)")
    typer.echo(status.detail)
    if check or not status.newer:
        if status.newer:
            typer.echo("Re-run without --check to install.")
        raise typer.Exit(code=0)
    if yes:
        approved = True
    elif sys.stdin.isatty():
        approved = typer.confirm(f"Upgrade {status.current} -> {status.latest}?", default=True)
    else:
        typer.echo("No TTY: pass --yes to upgrade.")
        raise typer.Exit(code=2)
    if not approved:
        typer.echo("Aborted.")
        raise typer.Exit(code=1)
    if verbose:
        typer.echo("pip install --upgrade openbundle")
    code = pip_upgrade(quiet=not verbose, show_logo=not no_banner)
    if code != 0:
        raise typer.Exit(code=code)
    typer.echo("Updated. Restart `openbundle serve` if it is running.")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
