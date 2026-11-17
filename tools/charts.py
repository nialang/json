#!/usr/bin/env python3
"""Draw the benchmark charts of the README from a results file of
tools/bench.py: parsing and writing throughput of this library and
serde_json, each relative to yyjson's on the same corpus.

    python tools/charts.py bench/results.json docs/images

Each chart is drawn twice, as NAME.svg on a light card and NAME-dark.svg on a
dark one, for a <picture> element to choose from by the reader's theme. Both
are self-contained SVG, readable on any page.
"""
import argparse
import json
import statistics
from pathlib import Path

# The corpora of each chart, in the order of the tables in docs/benchmarks.md.
CHARTS = {
    "parse": ("Parsing", [
        "small", "records-100k", "records-2m", "integers-100k", "strings-100k",
        "unicode-100k", "escapes-100k", "records-pretty", "records-tabs",
        "records-crlf", "mixed-100k",
    ]),
    "write": ("Writing", [
        "small", "records-100k", "integers-100k", "strings-100k", "unicode-100k",
        "escapes-100k", "mixed-100k",
    ]),
}
BASELINE = "yyjson"
# (implementation in the results, name shown, style class)
SERIES = [("nia", "json", "json"), ("serde", "serde_json", "serde")]

WIDTH = 780
PAD = 18
LABEL = 150
RIGHT = 70
TOP = 92
ROW = 36
BAR = 12
GAP = 3
SANS = "system-ui, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
THEMES = {
    "light": {
        "card": "#ffffff", "border": "#e4e0e8", "text": "#18161b", "muted": "#5f5a66",
        "grid": "#ece9ef", "json": "#b8235a", "serde": "#a19aa8",
    },
    "dark": {
        "card": "#18161b", "border": "#2e2a33", "text": "#ece9ef", "muted": "#a9a3b0",
        "grid": "#2e2a33", "json": "#f0709c", "serde": "#6f6876",
    },
}


def style(theme):
    c = THEMES[theme]
    # Value labels are outlined in the card color, so the yyjson line never
    # runs through their digits.
    return f"""
  .title {{ font: 600 16px {SANS}; fill: {c['text']}; }}
  .note {{ font: 12px {SANS}; fill: {c['muted']}; }}
  .label {{ font: 13px {MONO}; fill: {c['text']}; }}
  .value {{ font: 11px {SANS}; fill: {c['text']}; paint-order: stroke;
           stroke: {c['card']}; stroke-width: 3px; stroke-linejoin: round; }}
  .tick {{ font: 11px {SANS}; fill: {c['muted']}; }}
  .grid {{ stroke: {c['grid']}; stroke-width: 1; }}
  .baseline {{ stroke: {c['text']}; stroke-width: 1.5; stroke-dasharray: 4 3; }}
  .json {{ fill: {c['json']}; }}
  .serde {{ fill: {c['serde']}; }}
"""


def medians(results):
    """MB/s of each (implementation, mode, corpus)."""
    return {
        (sample["implementation"], sample["mode"], sample["corpus"]): sample["mb_per_second"]
        for sample in results["samples"]
    }


def chart(title, mode, names, speed, note, theme):
    ratios = []
    for name in names:
        base = speed[(BASELINE, mode, name)]
        ratios.append([speed[(implementation, mode, name)] / base for implementation, _, _ in SERIES])
    top = max(1.25, max(max(row) for row in ratios))
    scale_max = int(top * 2 + 0.999) / 2
    plot = WIDTH - LABEL - RIGHT
    x = lambda ratio: LABEL + plot * ratio / scale_max
    plot_bottom = TOP + ROW * len(names)
    height = plot_bottom + 40
    colors = THEMES[theme]
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {height}" '
        f'width="{WIDTH}" height="{height}" role="img" '
        f'aria-label="{title} throughput relative to yyjson">',
        f"<style>{style(theme)}</style>",
        f'<rect x="0.5" y="0.5" width="{WIDTH - 1}" height="{height - 1}" rx="8" '
        f'fill="{colors["card"]}" stroke="{colors["border"]}"/>',
        f'<text class="title" x="{PAD}" y="{PAD + 16}">{title} throughput relative to yyjson</text>',
        f'<text class="note" x="{PAD}" y="{PAD + 36}">{note}</text>',
    ]

    # Legend.
    legend_x = PAD
    for _, label, css in SERIES:
        out.append(f'<rect class="{css}" x="{legend_x}" y="{PAD + 48}" width="12" height="12" rx="2"/>')
        out.append(f'<text class="value" x="{legend_x + 17}" y="{PAD + 58}">{label}</text>')
        legend_x += 17 + 8 * len(label) + 20
    out.append(
        f'<line class="baseline" x1="{legend_x}" y1="{PAD + 54}" x2="{legend_x + 22}" y2="{PAD + 54}"/>'
    )
    out.append(f'<text class="value" x="{legend_x + 28}" y="{PAD + 58}">yyjson = 1x</text>')

    # Grid and ticks every half.
    tick = 0.0
    while tick <= scale_max + 1e-9:
        tx = x(tick)
        if tick != 1.0:
            out.append(f'<line class="grid" x1="{tx:.1f}" y1="{TOP - 4}" x2="{tx:.1f}" y2="{plot_bottom}"/>')
        out.append(
            f'<text class="tick" x="{tx:.1f}" y="{plot_bottom + 18}" text-anchor="middle">{tick:g}x</text>'
        )
        tick += 0.5

    # One row per corpus, a bar per series.
    for index, (name, row) in enumerate(zip(names, ratios)):
        y = TOP + ROW * index
        out.append(f'<text class="label" x="{LABEL - 12}" y="{y + BAR + 4}" text-anchor="end">{name}</text>')
        for series, ratio in enumerate(row):
            _, label, css = SERIES[series]
            by = y + series * (BAR + GAP)
            width = max(x(ratio) - LABEL, 1)
            out.append(
                f'<rect class="{css}" x="{LABEL}" y="{by}" width="{width:.1f}" height="{BAR}" rx="2">'
                f"<title>{label}: {ratio:.2f}x yyjson</title></rect>"
            )
            out.append(
                f'<text class="value" x="{LABEL + width + 5:.1f}" y="{by + BAR - 2}">{ratio:.2f}x</text>'
            )
    out.append(
        f'<line class="baseline" x1="{x(1.0):.1f}" y1="{TOP - 6}" x2="{x(1.0):.1f}" y2="{plot_bottom}"/>'
    )
    out.append("</svg>")
    return "\n".join(out) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("results", type=Path, help="a results file written by tools/bench.py")
    parser.add_argument("output", type=Path, help="the directory to write the charts to")
    parser.add_argument("--note", default="Median of five processes. Higher is faster.",
                        help="the line under each chart's title")
    args = parser.parse_args()
    speed = medians(json.loads(args.results.read_text(encoding="utf-8")))
    args.output.mkdir(parents=True, exist_ok=True)
    for mode, (title, names) in CHARTS.items():
        for theme, suffix in (("light", ""), ("dark", "-dark")):
            path = args.output / f"{mode}{suffix}.svg"
            path.write_text(chart(title, mode, names, speed, args.note, theme), encoding="utf-8", newline="\n")
        ratios = [speed[("nia", mode, name)] / speed[(BASELINE, mode, name)] for name in names]
        print(f"{mode}: json {min(ratios):.2f}-{max(ratios):.2f}x yyjson, "
              f"geometric mean {statistics.geometric_mean(ratios):.2f}x")


if __name__ == "__main__":
    main()
