from __future__ import annotations

import asyncio
import json
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from .banner import EXHAUST_BANNER
from .bench import run

console = Console()


def _banner() -> None:
    console.print(f"[bold magenta]{EXHAUST_BANNER}[/bold magenta]")


class BannerGroup(click.Group):
    def get_help(self, ctx: click.Context) -> str:
        _banner()
        return super().get_help(ctx)


@click.group(cls=BannerGroup)
def main() -> None:
    """MAD performance & load battery — нагрузочная панель агента."""


@main.command("run")
@click.argument("url")
@click.option("--threshold", "порог", default=3.0, show_default=True,
              help="во сколько раз p95 под нагрузкой может вырасти против baseline")
@click.option("--timeout", "таймаут", default=15.0, show_default=True)
@click.option("--json", "as_json", type=click.Path(), default=None,
              help="сохранить JSON-находки (контракт пайплайна)")
def run_cmd(url: str, порог: float, таймаут: float, as_json: str | None) -> None:
    """Нагрузочная кривая + ловушки, с вердиктом."""
    d = asyncio.run(run(url, порог_деградации=порог, таймаут=таймаут))
    if as_json:
        Path(as_json).write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

    # 🔴 rc=2 «не состоялась» ≠ rc=0 «чисто»
    if d["verdict"] == "НЕ ПРОВЕРЕНО":
        console.print(f"[yellow]НЕ ПРОВЕРЕНО[/yellow]: {d['not_proven']}")
        raise SystemExit(2)

    t = Table(title=f"exhaust: {url}  ·  нагрузочная кривая p95")
    t.add_column("конкурентность"); t.add_column("p50 ms"); t.add_column("p95 ms")
    t.add_column("таймаутов"); t.add_column("ошибок")
    for с in d["кривая"]:
        t.add_row(str(с["конкурентность"]), str(с["p50_ms"]), str(с["p95_ms"]),
                  str(с["таймаутов"]), str(с["ошибок"]))
    console.print(t)
    console.print(f"деградация p95: ×{d['деградация']} (baseline {d['baseline_p95_ms']} → "
                  f"пик {d['peak_p95_ms']} ms, порог ×{d['порог_деградации']})")

    провал = d["провал_ловушек"]
    if провал:
        console.print(f"[red]ловушки зависают/падают:[/red] {', '.join(провал)}")
    цвет = "red" if d["verdict"] == "ПРОВАЛ" else "green"
    console.print(f"Вердикт: [{цвет}]{d['verdict']}[/{цвет}] — {d['почему']}")
    console.print(f"[dim]{d['note']}[/dim]")

    if d["verdict"] == "ПРОВАЛ":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
