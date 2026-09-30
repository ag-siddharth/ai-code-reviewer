#!/usr/bin/env python3
"""
CLI entry point for the code reviewer.
"""

import click
import sys
import os
import subprocess
from pathlib import Path
from rich.console import Console
from rich.markdown import Markdown

from src.reviewer import review_file, review_files
from src.documenter import document_file
from src.utils import load_config, collect_files

console = Console()


@click.group()
@click.option("--config", "config_path", default="config.yaml", help="Path to config file")
@click.pass_context
def cli(ctx, config_path):
    """AI-powered code review and documentation tool."""
    ctx.ensure_object(dict)
    ctx.obj["config"] = load_config(config_path)


@cli.command()
@click.argument("path")
@click.option("--ext", default=None, help="File extensions to include (comma-separated)")
@click.option("--format", "output_format", default="text", type=click.Choice(["text", "markdown", "json"]))
@click.pass_context
def review(ctx, path, ext, output_format):
    """Review code files for issues and improvements."""
    cfg = ctx.obj["config"]

    target = Path(path)
    if not target.exists():
        console.print(f"[red]Error:[/red] {path} not found")
        sys.exit(1)

    extensions = ext.split(",") if ext else cfg.get("extensions", ["py", "ts"])

    if target.is_file():
        console.print(f"Reviewing [bold]{target.name}[/bold]...")
        results = review_file(target, cfg)
        _print_results([results], output_format)
    else:
        files = collect_files(target, extensions, cfg.get("ignore_dirs", []))
        max_files = cfg.get("max_files", 50)

        if len(files) > max_files:
            console.print(f"[yellow]Warning:[/yellow] Found {len(files)} files, limiting to {max_files}")
            files = files[:max_files]

        console.print(f"Reviewing [bold]{len(files)}[/bold] files...")
        results = review_files(files, cfg)
        _print_results(results, output_format)


@cli.command()
@click.argument("path")
@click.option("--inplace", is_flag=True, help="Modify the file in place")
@click.pass_context
def document(ctx, path, inplace):
    """Generate docstrings and comments for undocumented code."""
    cfg = ctx.obj["config"]

    target = Path(path)
    if not target.is_file():
        console.print(f"[red]Error:[/red] {path} is not a file")
        sys.exit(1)

    console.print(f"Documenting [bold]{target.name}[/bold]...")

    result = document_file(target, cfg)

    if result is None:
        console.print("Nothing to document — all functions already have docstrings.")
        return

    if inplace:
        target.write_text(result)
        console.print(f"[green]Updated[/green] {target}")
    else:
        output_path = target.with_suffix(f".documented{target.suffix}")
        output_path.write_text(result)
        console.print(f"[green]Written to[/green] {output_path}")


@cli.command()
@click.option("--base", default="main", help="Base branch to diff against")
@click.option("--format", "output_format", default="text", type=click.Choice(["text", "markdown", "json"]))
@click.pass_context
def diff(ctx, base, output_format):
    """Review only changed files in the current git diff."""
    cfg = ctx.obj["config"]

    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", base],
            capture_output=True, text=True, check=True
        )
    except subprocess.CalledProcessError:
        console.print("[red]Error:[/red] Not a git repo or branch not found")
        sys.exit(1)

    changed_files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]

    extensions = cfg.get("extensions", ["py", "ts"])
    files = [
        Path(f) for f in changed_files
        if Path(f).exists() and Path(f).suffix.lstrip(".") in extensions
    ]

    if not files:
        console.print("No reviewable files changed.")
        return

    console.print(f"Reviewing [bold]{len(files)}[/bold] changed files...")
    results = review_files(files, cfg)
    _print_results(results, output_format)


def _print_results(results, fmt):
    import json

    if fmt == "json":
        output = []
        for r in results:
            output.append({
                "file": str(r.get("file", "")),
                "comments": r.get("comments", []),
                "summary": r.get("summary", ""),
            })
        click.echo(json.dumps(output, indent=2))

    elif fmt == "markdown":
        for r in results:
            md = f"## {r.get('file', 'unknown')}\n\n"
            md += r.get("summary", "") + "\n\n"
            for c in r.get("comments", []):
                md += f"- **Line {c.get('line', '?')}**: {c.get('message', '')}\n"
            console.print(Markdown(md))

    else:
        for r in results:
            console.print(f"\n[bold cyan]{r.get('file', 'unknown')}[/bold cyan]")
            if r.get("summary"):
                console.print(f"  {r['summary']}")
            for c in r.get("comments", []):
                severity = c.get("severity", "info")
                color = {"error": "red", "warning": "yellow", "info": "blue"}.get(severity, "white")
                console.print(f"  [{color}]L{c.get('line', '?')}[/{color}]: {c.get('message', '')}")

        total_comments = sum(len(r.get("comments", [])) for r in results)
        console.print(f"\n[bold]{total_comments}[/bold] comments across {len(results)} files")


if __name__ == "__main__":
    cli()
