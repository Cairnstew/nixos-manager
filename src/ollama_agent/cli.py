"""Command-line interface for ollama_agent."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ollama_agent.config import AgentType, OllamaConfig
from ollama_agent.models import check_connection, list_models

app = typer.Typer(
    name="ollama-agent",
    help="Run local LLM agents via Ollama + smolagents.",
    add_completion=False,
)
console = Console()


@app.command()
def run(
    prompt: Annotated[str, typer.Argument(help="Task for the agent to solve.")],
    model: Annotated[str, typer.Option("--model", "-m")] = "qwen2.5-coder:7b",
    base_url: Annotated[str, typer.Option("--url")] = "http://localhost:11434",
    agent_type: Annotated[AgentType, typer.Option("--type", "-t")] = AgentType.CODE,
    max_steps: Annotated[int, typer.Option("--steps")] = 10,
    temperature: Annotated[float, typer.Option("--temp")] = 0.0,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
    tools: Annotated[str, typer.Option("--tools", help="Tool preset: minimal, coding, nixos, research, full")] = "minimal",
) -> None:
    """Run the agent on a single prompt and print the result."""
    from ollama_agent.agents.factory import create_agent
    from ollama_agent.tools import get_preset_tools, TOOL_PRESETS

    cfg = OllamaConfig(
        model=model,
        base_url=base_url,
        agent_type=agent_type,
        temperature=temperature,
        max_steps=max_steps,
        verbose=verbose,
    )

    try:
        tool_list = get_preset_tools(tools)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    tool_names = [t.name for t in tool_list]
    console.print(Panel(
        f"[bold cyan]Model:[/] {model}  "
        f"[bold cyan]Type:[/] {agent_type.value}  "
        f"[bold cyan]Tools:[/] {', '.join(tool_names)}"
    ))

    try:
        agent = create_agent(cfg, tools=tool_list)
        result = agent.run(prompt)
        console.print(Panel(str(result), title="[green]Result[/green]", border_style="green"))
    except Exception as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc


@app.command("list-models")
def list_models_cmd(
    base_url: Annotated[str, typer.Option("--url")] = "http://localhost:11434",
) -> None:
    """List all models available on the Ollama server."""
    try:
        models = list_models(base_url=base_url)
    except Exception as exc:
        console.print(f"[red]Could not connect to Ollama at {base_url}: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    table = Table(title="Available Ollama Models")
    table.add_column("Model", style="cyan")
    for name in sorted(models):
        table.add_row(name)
    console.print(table)


@app.command()
def check(
    model: Annotated[str, typer.Option("--model", "-m")] = "qwen2.5-coder:7b",
    base_url: Annotated[str, typer.Option("--url")] = "http://localhost:11434",
) -> None:
    """Check Ollama is reachable and the model is available."""
    ok = check_connection(model_id=model, base_url=base_url)
    if ok:
        console.print(f"[green]✓[/green] Model [bold]{model}[/bold] is available at {base_url}")
    else:
        console.print(
            f"[red]✗[/red] Model [bold]{model}[/bold] not found. "
            f"Run: [bold]ollama pull {model}[/bold]"
        )
        raise typer.Exit(code=1)


@app.command()
def serve(
    host: Annotated[str, typer.Option("--host")] = "0.0.0.0",
    port: Annotated[int, typer.Option("--port", "-p")] = 8000,
    reload: Annotated[bool, typer.Option("--reload")] = False,
) -> None:
    """Start the OpenAI-compatible HTTP server."""
    from ollama_agent.server import serve as _serve
    console.print(Panel(
        f"[bold green]ollama-agent server[/]\n"
        f"Listening on [cyan]http://{host}:{port}[/]\n"
        f"OpenAI base URL → [cyan]http://{host}:{port}/v1[/]"
    ))
    _serve(host=host, port=port, reload=reload)

@app.command("list-tools")
def list_tools_cmd() -> None:
    """List all available tools and presets."""
    from ollama_agent.tools import BUILTIN_TOOLS, TOOL_PRESETS

    table = Table(title="Built-in Tools")
    table.add_column("Name", style="cyan")
    table.add_column("Description")
    for name, cls in BUILTIN_TOOLS.items():
        table.add_row(name, cls.description[:80] + "..." if len(cls.description) > 80 else cls.description)
    console.print(table)

    table2 = Table(title="Presets")
    table2.add_column("Preset", style="green")
    table2.add_column("Tools")
    for preset, names in TOOL_PRESETS.items():
        table2.add_row(preset, ", ".join(names))
    console.print(table2)


if __name__ == "__main__":
    app()