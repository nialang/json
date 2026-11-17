#!/usr/bin/env python3
"""Draw the benchmark charts of the README and print the tables of
docs/benchmarks.md, from the results files of tools/bench.py:

    python tools/charts.py bench/results.json bench/memory.json docs/images

Each chart has one panel per document, with every library as a bar, fastest
or smallest first, and this library in color. It is drawn twice, as NAME.svg
on a light card and NAME-dark.svg on a dark one, for a <picture> element to
choose from by the reader's theme; both are self-contained SVG.
"""
import argparse
import json
from pathlib import Path

# The name each harness is shown by, in the order of the tables.
NAMES = {
    "nia": "json",
    "yyjson": "yyjson",
    "simdjson": "simdjson",
    "rapidjson": "RapidJSON",
    "sonic": "sonic-rs",
    "serde": "serde_json",
    "nlohmann": "nlohmann/json",
    "cjson": "cJSON",
}
# The documents of the charts: the real-world documents of
# nativejson-benchmark and the generated API feed.
SPEED_PANELS = ["twitter", "citm_catalog", "canada", "mixed-100k"]
MEMORY_PANELS = ["twitter", "citm_catalog", "canada", "mixed-20m"]

WIDTH = 780
PAD = 18
GUTTER = 28
TOP = 74
ROW = 22
BAR = 14
LABEL = 104
SANS = "system-ui, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"
THEMES = {
    "light": {"card": "#ffffff", "border": "#e4e0e8", "text": "#18161b", "muted": "#5f5a66",
              "json": "#b8235a", "other": "#c9c3cf"},
    "dark": {"card": "#18161b", "border": "#2e2a33", "text": "#ece9ef", "muted": "#a9a3b0",
             "json": "#f0709c", "other": "#4a4550"},
}


def style(theme):
    c = THEMES[theme]
    return f"""
  .title {{ font: 600 16px {SANS}; fill: {c['text']}; }}
  .note {{ font: 12px {SANS}; fill: {c['muted']}; }}
  .panel {{ font: 600 13px {SANS}; fill: {c['text']}; }}
  .label {{ font: 12px {SANS}; fill: {c['muted']}; }}
  .label.json {{ font-weight: 600; fill: {c['text']}; }}
  .value {{ font: 11px {SANS}; fill: {c['muted']}; }}
  .value.json {{ font-weight: 600; fill: {c['text']}; }}
  .bar {{ fill: {c['other']}; }}
  .bar.json {{ fill: {c['json']}; }}
"""


def escape(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def chart(title, note, panels, theme, lower_is_better, unit):
    """`panels` is a list of (document, {implementation: value})."""
    colors = THEMES[theme]
    implementations = max(len(values) for _, values in panels)
    panel_height = 26 + ROW * implementations
    rows = (len(panels) + 1) // 2
    height = TOP + rows * (panel_height + 18) + 6
    panel_width = (WIDTH - 2 * PAD - GUTTER) // 2
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {height}" '
        f'width="{WIDTH}" height="{height}" role="img" aria-label="{escape(title)}">',
        f"<style>{style(theme)}</style>",
        f'<rect x="0.5" y="0.5" width="{WIDTH - 1}" height="{height - 1}" rx="8" '
        f'fill="{colors["card"]}" stroke="{colors["border"]}"/>',
        f'<text class="title" x="{PAD}" y="{PAD + 16}">{escape(title)}</text>',
        f'<text class="note" x="{PAD}" y="{PAD + 36}">{escape(note)}</text>',
    ]
    for index, (document, values) in enumerate(panels):
        left = PAD + (index % 2) * (panel_width + GUTTER)
        top = TOP + (index // 2) * (panel_height + 18)
        out.append(f'<text class="panel" x="{left}" y="{top + 12}">{escape(document)}</text>')
        ordered = sorted(values.items(), key=lambda item: item[1], reverse=not lower_is_better)
        largest = max(values.values())
        plot = panel_width - LABEL - 64
        for row, (implementation, value) in enumerate(ordered):
            y = top + 24 + row * ROW
            css = " json" if implementation == "nia" else ""
            name = NAMES[implementation]
            width = max(plot * value / largest, 1)
            shown = unit(value)
            out.append(f'<text class="label{css}" x="{left + LABEL - 8}" y="{y + BAR - 3}" '
                       f'text-anchor="end">{escape(name)}</text>')
            out.append(f'<rect class="bar{css}" x="{left + LABEL}" y="{y}" width="{width:.1f}" '
                       f'height="{BAR}" rx="2"><title>{escape(name)}: {shown}</title></rect>')
            out.append(f'<text class="value{css}" x="{left + LABEL + width + 5:.1f}" '
                       f'y="{y + BAR - 3}">{shown}</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def speeds(results, mode):
    table = {}
    for sample in results["samples"]:
        if sample["mode"] == mode:
            table.setdefault(sample["corpus"], {})[sample["implementation"]] = sample["mb_per_second"]
    return table


def memory(results):
    table = {}
    for sample in results["samples"]:
        table.setdefault(sample["corpus"], {})[sample["implementation"]] = sample["bytes_per_input_byte"]
    return table


def markdown(table, implementations, cell, lower_is_better):
    """A markdown table with this library's rank among them last."""
    head = "| Document | " + " | ".join(NAMES[name] for name in implementations) + " | json's rank |"
    rule = "| --- | " + " | ".join("---:" for _ in implementations) + " | ---: |"
    lines = [head, rule]
    for document, values in table.items():
        ordered = sorted(values.values(), reverse=not lower_is_better)
        rank = ordered.index(values["nia"]) + 1
        cells = " | ".join(cell(values[name]) if name in values else "" for name in implementations)
        lines.append(f"| {document} | {cells} | {rank} of {len(values)} |")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("speed", type=Path, help="a results file of tools/bench.py")
    parser.add_argument("memory", type=Path, help="a results file of tools/bench.py --memory")
    parser.add_argument("output", type=Path, help="the directory to write the charts to")
    parser.add_argument("--machine", default="Intel Core i9-13900HX, Linux under WSL 2",
                        help="the machine the results come from, named under each title")
    args = parser.parse_args()
    speed = json.loads(args.speed.read_text(encoding="utf-8"))
    used = json.loads(args.memory.read_text(encoding="utf-8"))
    implementations = [name for name in NAMES if name in speed["implementations"]]
    parse, write, sizes = speeds(speed, "parse"), speeds(speed, "write"), memory(used)
    rate = lambda value: f"{value:,.0f} MB/s"
    ratio = lambda value: f"{value:.2f}x"
    charts = {
        "parse": ("Parsing throughput, MB/s of input",
                  f"Median of five processes on {args.machine}. Longer is faster.",
                  [(name, parse[name]) for name in SPEED_PANELS], False, rate),
        "write": ("Writing throughput, MB/s of input",
                  f"A parsed document as compact text into memory; median of five processes on "
                  f"{args.machine}. Longer is faster.",
                  [(name, write[name]) for name in SPEED_PANELS], False, rate),
        "memory": ("Memory of a parsed document, per byte of input",
                   f"Peak resident memory added by parsing; median of five processes on {args.machine}. "
                   "Shorter is smaller.",
                   [(name, sizes[name]) for name in MEMORY_PANELS], True, ratio),
    }
    args.output.mkdir(parents=True, exist_ok=True)
    for name, (title, note, panels, lower, unit) in charts.items():
        for theme, suffix in (("light", ""), ("dark", "-dark")):
            path = args.output / f"{name}{suffix}.svg"
            path.write_text(chart(title, note, panels, theme, lower, unit), encoding="utf-8", newline="\n")
    print("### Parsing, MB/s\n")
    print(markdown(parse, implementations, lambda value: f"{value:,.0f}", False))
    print("\n### Writing, MB/s\n")
    print(markdown(write, implementations, lambda value: f"{value:,.0f}", False))
    print("\n### Memory, bytes per byte of input\n")
    print(markdown(sizes, implementations, lambda value: f"{value:.2f}", True))


if __name__ == "__main__":
    main()
