# Performance

Numbers come from `scripts/bench.py`:

```bash
make bench                                                    # 100 / 1k / 10k / 50k, median of 5
uv run python scripts/bench.py matrix --shape chain --sizes 1000,3000 --repeat 1
```

Each run is its own process, so peak memory is for that plan only. Stage times are wall seconds;
`total s` is reading the file, parsing, analysis and all four renderers.

## Results

AMD Ryzen 5 7535HS laptop (tf-diff is single-threaded), Windows 11, Python 3.14.8, machine in
normal use, so allow ~15% noise. Rows up to 10k are the median of 3 runs, 50k is a single run.

Plans are generated (`mixed` shape): ten `for_each` module calls, ten resources per instance,
cross-module references and one VPC everything hangs off. 84% of resources are unchanged, like a
typical PR. `planned_values` and `prior_state` are included, so file sizes are close to real
`terraform show -json` output.

| resources | changed | findings | edges | plan MB | json | graph | parse | analyze | terminal | JSON | Markdown | SARIF | total s | peak MB |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 102 | 21 | 6 | 101 | 0.3 | 0.00 | 0.01 | 0.02 | 0.00 | 0.02 | 0.00 | 0.00 | 0.00 | 0.17 | 43 |
| 1,002 | 167 | 21 | 1,010 | 2.6 | 0.02 | 0.01 | 0.14 | 0.04 | 0.06 | 0.00 | 0.00 | 0.00 | 0.40 | 57 |
| 10,002 | 1,649 | 210 | 10,100 | 25.5 | 0.25 | 0.12 | 1.64 | 0.73 | 0.85 | 0.04 | 0.01 | 0.01 | 4.44 | 215 |
| 50,002 | 8,235 | 1,050 | 50,500 | 127.9 | 1.25 | 2.01 | 12.62 | 3.83 | 3.20 | 0.20 | 0.04 | 0.02 | 26.38 | 921 |

`json` is just `json.loads`, `graph` is just building the dependency graph. `parse` includes both
plus validation and flattening.

## Notes

Analysis and rendering grow ~5x from 10k to 50k. Parsing and the graph grow faster (~8x and
~17x). That's a single run with ~1 GB in use, so it may be memory pressure; I haven't dug into it
yet.

Parsing is ~40% of a run. Decoding JSON is cheap; the time goes into flattening `before` /
`after` of changed resources, with their unknown and sensitive masks, into path/value pairs.
Two things roughly halved parse time: unchanged resources only keep their tags, since that's all
the analysis reads from them, and GC is off while parsing, since the parser allocates millions of
objects with no cycles.

Peak memory is ~7-8x the plan file: decoded JSON, validated model and flattened attributes all
live at once during parsing. A plan at the 512 MiB limit would need ~4 GB.

Terminal output costs ~3-4 ms per finding. Markdown and SARIF, the CI formats, stay under 0.1 s
even at 50k.

## Limits

Every changed resource gets its own blast radius and the JSON lists all its dependents. In a long
chain where everything changes, time and output grow quadratically: 3,000 resources in a chain
take 3 s to analyze and give a 165 MB JSON report. Real stacks are shallow (VPC, subnet,
instance, attachment) and a 3,000-wide fan-out takes 1.1 s end to end, so I haven't optimized
this.

SARIF keeps the 25,000 most severe results, GitHub's limit per run, and says how many were
dropped.
