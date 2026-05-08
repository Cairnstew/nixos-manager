"""Command-line interface for ollama_agent."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ollama_agent.config import AgentType, OllamaConfig
from ollama_agent.models import OllamaModel

app = typer.Typer(
    name="ollama-agent",
    help="Run local LLM agents via Ollama + smolagents.",
    add_completion=False,
)
console = Console()


@app.command()
def run(
    prompt: Annotated[str, typer.Argument(help="Task for the agent to solve.")],
    model: Annotated[str, typer.Option("--model", "-m")] = "qwen2.5:7b",
    base_url: Annotated[str, typer.Option("--url")] = "http://localhost:11434",
    agent_type: Annotated[AgentType, typer.Option("--type", "-t")] = AgentType.CODE,
    max_steps: Annotated[int, typer.Option("--steps")] = 10,
    temperature: Annotated[float, typer.Option("--temp")] = 0.0,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Run the agent on a single prompt and print the result."""
    from ollama_agent.agents.factory import create_agent

    cfg = OllamaConfig(
        model=model,
        base_url=base_url,
        agent_type=agent_type,
        temperature=temperature,
        max_steps=max_steps,
        verbose=verbose,
    )

    console.print(Panel(f"[bold cyan]Model:[/] {model}  [bold cyan]Type:[/] {agent_type.value}"))

    try:
        agent = create_agent(cfg)
        result = agent.run(prompt)
        console.print(Panel(str(result), title="[green]Result[/green]", border_style="green"))
    except Exception as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc


@app.command("list-models")
def list_models(
    base_url: Annotated[str, typer.Option("--url")] = "http://localhost:11434",
) -> None:
    """List all models available on the Ollama server."""
    m = OllamaModel(base_url=base_url)
    try:
        models = m.list_models()
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
    model: Annotated[str, typer.Option("--model", "-m")] = "qwen2.5:7b",
    base_url: Annotated[str, typer.Option("--url")] = "http://localhost:11434",
) -> None:
    """Check Ollama is reachable and the model is available."""
    m = OllamaModel(model_id=model, base_url=base_url)
    ok = m.check_connection()
    if ok:
        console.print(f"[green]✓[/green] Model [bold]{model}[/bold] is available at {base_url}")
    else:
        console.print(
            f"[red]✗[/red] Model [bold]{model}[/bold] not found. "
            f"Run: [bold]ollama pull {model}[/bold]"
        )
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()