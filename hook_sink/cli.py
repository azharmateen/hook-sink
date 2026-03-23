"""CLI for hook-sink: local webhook catcher."""

import json
import sys

import click
from rich.console import Console
from rich.table import Table
from rich.syntax import Syntax
from rich.panel import Panel

from .storage import WebhookStorage
from .replayer import Replayer

console = Console()


def get_storage(db: str = None) -> WebhookStorage:
    return WebhookStorage(db_path=db)


@click.group()
@click.option("--db", default=None, help="Path to SQLite database file")
@click.pass_context
def cli(ctx, db):
    """hook-sink: Local webhook catcher - receive, inspect, edit, and replay webhooks."""
    ctx.ensure_object(dict)
    ctx.obj["db"] = db


@cli.command()
@click.option("--port", "-p", default=8765, help="Port to listen on")
@click.option("--host", "-h", default="0.0.0.0", help="Host to bind to")
@click.pass_context
def serve(ctx, port, host):
    """Start the webhook catcher server with web dashboard."""
    import uvicorn
    from .server import set_storage

    storage = get_storage(ctx.obj["db"])
    set_storage(storage)

    console.print(f"\n[bold green]hook-sink[/bold green] listening on [cyan]http://{host}:{port}[/cyan]\n")
    console.print(f"  Dashboard:  [link]http://localhost:{port}/[/link]")
    console.print(f"  Catch URL:  [link]http://localhost:{port}/hook/your-path[/link]")
    console.print(f"  API:        [link]http://localhost:{port}/api/webhooks[/link]")
    console.print(f"\n  Example:")
    console.print(f'  curl -X POST http://localhost:{port}/hook/github -H "Content-Type: application/json" -d \'{{"event":"push"}}\'')
    console.print()

    # Import dashboard to register routes
    from . import dashboard  # noqa: F401

    uvicorn.run("hook_sink.server:app", host=host, port=port, log_level="info")


@cli.command("list")
@click.option("--limit", "-n", default=20, help="Number of webhooks to show")
@click.option("--path", "-p", default=None, help="Filter by path")
@click.option("--method", "-m", default=None, help="Filter by HTTP method")
@click.option("--search", "-s", default=None, help="Search body content")
@click.pass_context
def list_webhooks(ctx, limit, path, method, search):
    """List captured webhooks."""
    storage = get_storage(ctx.obj["db"])

    if path or method or search:
        webhooks = storage.search(path=path, method=method, body_contains=search)
    else:
        webhooks = storage.list_all(limit=limit)

    if not webhooks:
        console.print("[yellow]No webhooks captured yet.[/yellow]")
        return

    table = Table(title=f"Captured Webhooks ({storage.count()} total)")
    table.add_column("ID", style="cyan", width=12)
    table.add_column("Method", width=7)
    table.add_column("Path", style="white")
    table.add_column("Size", justify="right")
    table.add_column("Source", style="dim")
    table.add_column("Time", style="dim")

    method_colors = {
        "POST": "green", "PUT": "yellow", "PATCH": "magenta",
        "DELETE": "red", "GET": "blue",
    }

    for w in webhooks:
        color = method_colors.get(w.method, "white")
        table.add_row(
            w.id,
            f"[{color}]{w.method}[/{color}]",
            w.path,
            _format_bytes(w.body_size),
            w.source_ip,
            w.timestamp_iso[11:19],
        )

    console.print(table)


@cli.command()
@click.argument("webhook_id")
@click.pass_context
def inspect(ctx, webhook_id):
    """Inspect a captured webhook in detail."""
    storage = get_storage(ctx.obj["db"])
    w = storage.get(webhook_id)

    if w is None:
        console.print(f"[red]Webhook {webhook_id} not found.[/red]")
        sys.exit(1)

    # Provider detection
    from .validator import SignatureValidator
    provider = SignatureValidator.detect_provider(w.headers)

    console.print(Panel(
        f"[bold]{w.method}[/bold] {w.path}\n"
        f"From: {w.source_ip} | Size: {_format_bytes(w.body_size)} | "
        f"Time: {w.timestamp_iso}"
        + (f" | Provider: [cyan]{provider}[/cyan]" if provider else ""),
        title=f"Webhook {w.id}",
        border_style="cyan",
    ))

    # Headers
    header_table = Table(title="Headers", show_header=True, header_style="bold")
    header_table.add_column("Name", style="cyan")
    header_table.add_column("Value")
    for k, v in w.headers.items():
        header_table.add_row(k, v)
    console.print(header_table)

    # Body
    if w.body:
        body_display = w.body
        lang = "text"
        if w.body_json is not None:
            body_display = json.dumps(w.body_json, indent=2)
            lang = "json"
        console.print(Panel(
            Syntax(body_display, lang, theme="monokai", word_wrap=True),
            title="Body",
            border_style="green",
        ))

    # Query params
    if w.query_params:
        console.print(Panel(
            Syntax(json.dumps(w.query_params, indent=2), "json", theme="monokai"),
            title="Query Parameters",
            border_style="yellow",
        ))


@cli.command()
@click.argument("webhook_id")
@click.option("--target", "-t", required=True, help="Target URL to replay to")
@click.option("--patch", "-p", multiple=True, help="JSON patch: key=value (dot notation for nested)")
@click.pass_context
def replay(ctx, webhook_id, target, patch):
    """Replay a captured webhook to a target URL."""
    storage = get_storage(ctx.obj["db"])

    # Parse patches
    patches = {}
    for p in patch:
        if "=" not in p:
            console.print(f"[red]Invalid patch format: {p}. Use key=value[/red]")
            sys.exit(1)
        key, _, value = p.partition("=")
        # Try to parse value as JSON
        try:
            patches[key] = json.loads(value)
        except json.JSONDecodeError:
            patches[key] = value

    replayer = Replayer(storage)
    result = replayer.replay(webhook_id, target, patches=patches if patches else None)

    if result.success:
        console.print(f"\n[green]Replay successful![/green]")
        console.print(f"  Status: [cyan]{result.status_code}[/cyan]")
        console.print(f"  Time:   [cyan]{result.elapsed_ms:.1f}ms[/cyan]")
        console.print(f"  Target: {result.target_url}")
        if result.response_body:
            try:
                body = json.dumps(json.loads(result.response_body), indent=2)
                console.print(Panel(
                    Syntax(body, "json", theme="monokai"),
                    title="Response",
                ))
            except json.JSONDecodeError:
                console.print(f"\n{result.response_body[:500]}")
    else:
        console.print(f"\n[red]Replay failed![/red]")
        if result.error:
            console.print(f"  Error: {result.error}")
        if result.status_code:
            console.print(f"  Status: {result.status_code}")


@cli.command()
@click.confirmation_option(prompt="Delete all captured webhooks?")
@click.pass_context
def clear(ctx):
    """Clear all captured webhooks."""
    storage = get_storage(ctx.obj["db"])
    count = storage.clear()
    console.print(f"[green]Deleted {count} webhook(s).[/green]")


def _format_bytes(b: int) -> str:
    if b == 0:
        return "0 B"
    for unit in ["B", "KB", "MB"]:
        if b < 1024:
            return f"{b:.0f} {unit}" if unit == "B" else f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} GB"


if __name__ == "__main__":
    cli()
