# EmulatorRomsPacker

Python script for GoodTools/GoodMerge ROM archives. It opens each `.zip` or `.7z`
archive, selects one ROM by user-defined language, dump quality and region
priorities, renames it to a clean game title, then repacks it as `.7z` or `.zip`
into the output directory.

## Usage

Run on Windows:

```cmd
run.cmd
```

Run on Linux/macOS/*nix:

```sh
chmod +x ./run.sh
./run.sh
```

Both scripts create `.venv`, install dependencies from `requirements.txt`, then
run:

```sh
python main.py --config config.json
```

Large ROM sets can be processed in parallel. Set `workers` in `config.json` or
override it from the command line:

```cmd
run.cmd --workers 4
```

```sh
./run.sh --workers 4
```

Skipped archives and processing errors are written as JSON Lines when `log_file`
is set in `config.json`:

```json
"log_file": "output/roms_packer.events.jsonl"
```

Each record includes the archive path, reason, member count and ROM candidate
count, so failed runs can be analyzed after processing.

Extra CLI arguments are passed through to `main.py`, so dry-run is:

```cmd
run.cmd --dry-run
```

```sh
./run.sh --dry-run
```

Manual run with an existing Python environment:

```powershell
pip install -r requirements.txt
python main.py --config config.json
```

## Selection

Default priorities are:

```json
{
  "language_priority": ["original"],
  "quality_priority": [
    "verified",
    "good-checksum",
    "unknown",
    "translation",
    "alternate",
    "fixed",
    "overdump",
    "pirate",
    "hack",
    "trained",
    "bad"
  ],
  "region_priority": ["U", "E", "W", "J"],
  "selection_order": ["language", "quality", "region", "revision"]
}
```

This means clean verified dumps win over bad dumps before region is considered.
If both candidates have the same language and quality, `(U)` is preferred; if it
is missing, `(E)` is used; then `(W)` and `(J)`.

If you want strict region-first behavior, set:

```json
"selection_order": ["language", "region", "quality", "revision"]
```

Supported quality aliases include `verified` (`[!]`), `good-checksum` (`[c]`),
`translation` (`[T+Rus]`, `[T-Fre]`), `alternate` (`[a]`), `fixed` (`[f]`),
`hack` (`[h]`), `overdump` (`[o]`), `pirate` (`[p]`), `trained` (`[t]`), and
`bad` (`[b]`).

GoodTools references used for these tags:

- https://en.everybodywiki.com/GoodTools
- https://datacrystal.tcrf.net/wiki/GoodTools
