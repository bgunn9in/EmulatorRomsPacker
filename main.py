#!/usr/bin/env python

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable


ARCHIVE_EXTENSIONS = {".zip", ".7z"}
DEFAULT_ROM_EXTENSIONS = {
    ".bin",
    ".gen",
    ".md",
    ".smd",
    ".32x",
    ".nes",
    ".fds",
    ".smc",
    ".sfc",
    ".fig",
    ".swc",
}
DEFAULT_REGION_PRIORITY = ["U", "E", "W", "J"]
DEFAULT_LANGUAGE_PRIORITY = ["original"]
DEFAULT_QUALITY_PRIORITY = [
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
    "bad",
]
DEFAULT_SELECTION_ORDER = ["language", "quality", "region", "revision"]
SUPPORTED_SELECTION_KEYS = {"language", "quality", "region", "revision"}
REGION_ALIASES = {
    "USA": "U",
    "US": "U",
    "UNITED STATES": "U",
    "EU": "E",
    "EUR": "E",
    "EUROPE": "E",
    "JAPAN": "J",
    "WORLD": "W",
    "ANY": "*",
    "*": "*",
}
LANGUAGE_ALIASES = {
    "": "original",
    "none": "original",
    "original": "original",
    "orig": "original",
    "vanilla": "original",
}
QUALITY_ALIASES = {
    "!": ["!"],
    "verified": ["!"],
    "good": ["!"],
    "good-dump": ["!"],
    "good-checksum": ["c"],
    "checksum-good": ["c"],
    "alternate": ["a"],
    "alternative": ["a"],
    "bad": ["b"],
    "bad-dump": ["b"],
    "fixed": ["f"],
    "fix": ["f"],
    "hack": ["h"],
    "hacked": ["h"],
    "overdump": ["o"],
    "overdumped": ["o"],
    "pirate": ["p"],
    "pirated": ["p"],
    "trained": ["t"],
    "trainer": ["t"],
    "translation": ["T"],
    "translated": ["T"],
    "pending": ["!p"],
    "bad-checksum": ["x"],
    "checksum-bad": ["x"],
}
QUALITY_PENALTY = {
    "b": 100,
    "x": 80,
    "h": 50,
    "t": 40,
    "p": 30,
    "f": 20,
    "o": 10,
    "a": 5,
    "T": 5,
    "!p": 3,
}
COUNTRY_CODES = {
    "A",
    "AS",
    "B",
    "C",
    "CH",
    "D",
    "E",
    "F",
    "G",
    "GR",
    "HK",
    "I",
    "J",
    "K",
    "NL",
    "NO",
    "R",
    "S",
    "SW",
    "U",
    "UK",
    "W",
    "UNL",
    "UNK",
    "PD",
}
ROUND_METADATA_TAGS = {
    "32X",
    "ALPHA",
    "ALT MUSIC",
    "BETA",
    "BIOS",
    "CART",
    "DEMO",
    "FDS HACK",
    "GG2SMS",
    "J-CART",
    "KIOSK DEMO",
    "MARS SAMPLE PROGRAM",
    "MB",
    "MENU",
    "MP",
    "N64DD",
    "NP",
    "NSS",
    "NTSC",
    "OLD",
    "PAL",
    "PC10",
    "PRE-RELEASE",
    "PROTOTYPE",
    "REVXB",
    "SC-3000",
    "SF-7000",
    "SG-1000",
    "SIMP",
    "SN",
    "ST",
    "VS",
}

ROUND_TAG_RE = re.compile(r"\(([^()]*)\)")
SQUARE_TAG_RE = re.compile(r"\[([^\[\]]*)\]")
INVALID_FILENAME_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
REVISION_RE = re.compile(r"^(?:REV|PRG)(\d+)$", re.IGNORECASE)
TRANSLATION_RE = re.compile(r"^(?:T[+-]|R-)([A-Za-z]+)", re.IGNORECASE)


@dataclass(frozen=True)
class AppConfig:
    input_dir: Path
    output_dir: Path
    archive_format: str
    region_priority: list[str]
    language_priority: list[str]
    quality_priority: list[str]
    selection_order: list[str]
    rom_extensions: set[str]
    recursive: bool
    overwrite: bool
    dry_run: bool
    prefer_revision: str
    workers: int


@dataclass(frozen=True)
class RomCandidate:
    archive_path: Path
    member_name: str
    file_extension: str
    clean_title: str
    round_tags: list[str]
    square_tags: list[str]
    regions: list[str]
    languages: list[str]
    revision: int | None


@dataclass(frozen=True)
class ProcessResult:
    archive_path: Path
    selected: RomCandidate | None
    output_path: Path | None
    reason: str


def parse_csv(value: str | Iterable[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = value.split(",")
    else:
        parts = []
        for item in value:
            parts.extend(str(item).split(","))
    return [part.strip() for part in parts if part.strip()]


def normalize_region(value: str) -> str:
    raw = value.strip()
    return REGION_ALIASES.get(raw.upper(), raw.upper())


def normalize_language(value: str) -> str:
    raw = value.strip()
    return LANGUAGE_ALIASES.get(raw.lower(), raw.lower())


def normalize_quality(value: str) -> str:
    return value.strip().strip("[]")


def normalize_extension(value: str) -> str:
    raw = value.strip().lower()
    if not raw:
        return raw
    return raw if raw.startswith(".") else f".{raw}"


def load_json_config(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except OSError as exc:
        raise SystemExit(f"Cannot read config {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON config {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit("JSON config must be an object.")
    return data


def config_get(data: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in data:
            return data[name]
    return None


def bool_override(current: bool, value: bool | None) -> bool:
    return current if value is None else value


def build_config(args: argparse.Namespace) -> AppConfig:
    data = load_json_config(args.config)

    input_dir = args.input or config_get(data, "input_dir", "input", "roms_dir") or "input"
    output_dir = args.output or config_get(data, "output_dir", "output") or "output"
    archive_format = (
        args.archive_format
        or config_get(data, "archive_format", "format", "compression")
        or "7z"
    ).lower()
    if archive_format not in {"zip", "7z"}:
        raise SystemExit("archive_format must be 'zip' or '7z'.")

    cli_regions = parse_csv(args.regions)
    region_priority = cli_regions or parse_csv(
        config_get(data, "region_priority", "regions")
    )
    region_priority = [normalize_region(region) for region in region_priority]
    if not region_priority:
        region_priority = DEFAULT_REGION_PRIORITY.copy()

    cli_languages = parse_csv(args.languages)
    language_priority = cli_languages or parse_csv(
        config_get(data, "language_priority", "languages")
    )
    if cli_languages and "original" not in [
        normalize_language(item) for item in language_priority
    ]:
        language_priority.append("original")
    language_priority = [normalize_language(language) for language in language_priority]
    if not language_priority:
        language_priority = DEFAULT_LANGUAGE_PRIORITY.copy()

    quality_priority = parse_csv(args.qualities) or parse_csv(
        config_get(data, "quality_priority", "qualities")
    )
    quality_priority = [normalize_quality(quality) for quality in quality_priority]
    if not quality_priority:
        quality_priority = DEFAULT_QUALITY_PRIORITY.copy()

    selection_order = parse_csv(args.selection_order) or parse_csv(
        config_get(data, "selection_order")
    )
    selection_order = [item.lower() for item in selection_order]
    if not selection_order:
        selection_order = DEFAULT_SELECTION_ORDER.copy()
    unknown_keys = [key for key in selection_order if key not in SUPPORTED_SELECTION_KEYS]
    if unknown_keys:
        raise SystemExit(
            "Unsupported selection_order keys: "
            + ", ".join(unknown_keys)
            + ". Use language, quality, region, revision."
        )

    rom_extensions = parse_csv(args.rom_extensions) or parse_csv(
        config_get(data, "rom_extensions")
    )
    extensions = {normalize_extension(extension) for extension in rom_extensions}
    extensions = {extension for extension in extensions if extension}
    if not extensions:
        extensions = DEFAULT_ROM_EXTENSIONS.copy()

    recursive = bool(config_get(data, "recursive") or False)
    recursive = bool_override(recursive, args.recursive)
    overwrite = bool(config_get(data, "overwrite") or False)
    overwrite = bool_override(overwrite, args.overwrite)
    dry_run = bool(config_get(data, "dry_run") or False)
    dry_run = bool_override(dry_run, args.dry_run)
    prefer_revision = (
        args.prefer_revision
        or config_get(data, "prefer_revision")
        or "newest"
    ).lower()
    if prefer_revision not in {"newest", "oldest", "none"}:
        raise SystemExit("prefer_revision must be newest, oldest or none.")

    workers = args.workers if args.workers is not None else config_get(data, "workers")
    if workers is None:
        workers = 1
    try:
        workers = int(workers)
    except (TypeError, ValueError) as exc:
        raise SystemExit("workers must be a positive integer.") from exc
    if workers < 1:
        raise SystemExit("workers must be a positive integer.")

    return AppConfig(
        input_dir=Path(input_dir),
        output_dir=Path(output_dir),
        archive_format=archive_format,
        region_priority=region_priority,
        language_priority=language_priority,
        quality_priority=quality_priority,
        selection_order=selection_order,
        rom_extensions=extensions,
        recursive=recursive,
        overwrite=overwrite,
        dry_run=dry_run,
        prefer_revision=prefer_revision,
        workers=workers,
    )


def create_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Select one ROM from each GoodTools/GoodMerge archive and repack it."
    )
    parser.add_argument("-c", "--config", type=Path, help="Path to JSON config.")
    parser.add_argument("-i", "--input", help="Input directory with .zip/.7z archives.")
    parser.add_argument("-o", "--output", help="Output directory for repacked archives.")
    parser.add_argument(
        "-f",
        "--format",
        dest="archive_format",
        choices=["zip", "7z"],
        help="Output archive format.",
    )
    parser.add_argument(
        "-r",
        "--regions",
        "--region",
        dest="regions",
        help="Comma-separated region priority, for example U,E,W,J.",
    )
    parser.add_argument(
        "-l",
        "--languages",
        "--language",
        dest="languages",
        help="Comma-separated translation priority, for example Rus,Eng,original.",
    )
    parser.add_argument(
        "-q",
        "--qualities",
        "--quality",
        dest="qualities",
        help="Comma-separated quality priority, for example verified,translation,unknown,bad.",
    )
    parser.add_argument(
        "--selection-order",
        help="Comma-separated score order: language,quality,region,revision.",
    )
    parser.add_argument(
        "--rom-extensions",
        help="Comma-separated ROM extensions to consider.",
    )
    parser.add_argument(
        "--recursive",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Scan input directory recursively.",
    )
    parser.add_argument(
        "--overwrite",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Overwrite existing output archives.",
    )
    parser.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Show selected ROMs without writing output archives.",
    )
    parser.add_argument(
        "--prefer-revision",
        choices=["newest", "oldest", "none"],
        help="Tie-breaker for REV/PRG tags.",
    )
    parser.add_argument(
        "-j",
        "--workers",
        type=int,
        help="Number of archives to process in parallel.",
    )
    return parser


def find_archives(input_dir: Path, recursive: bool) -> list[Path]:
    iterator = input_dir.rglob("*") if recursive else input_dir.glob("*")
    return sorted(
        path
        for path in iterator
        if path.is_file() and path.suffix.lower() in ARCHIVE_EXTENSIONS
    )


def list_archive_members(archive_path: Path) -> list[str]:
    suffix = archive_path.suffix.lower()
    if suffix == ".zip":
        with zipfile.ZipFile(archive_path, "r") as archive:
            return [
                item.filename
                for item in archive.infolist()
                if not item.is_dir()
            ]
    if suffix == ".7z":
        try:
            import py7zr
        except ImportError as exc:
            raise RuntimeError(
                "py7zr is required to read .7z archives. Install it with: pip install py7zr"
            ) from exc
        with py7zr.SevenZipFile(archive_path, "r") as archive:
            return [
                item.filename
                for item in archive.list()
                if item.is_file and not item.is_symlink
            ]
    raise RuntimeError(f"Unsupported archive type: {archive_path}")


def strip_archive_path(member_name: str) -> str:
    return re.split(r"[\\/]+", member_name)[-1]


def clean_game_title(member_name: str) -> str:
    filename = strip_archive_path(member_name)
    stem = Path(filename).stem
    cleaned = SQUARE_TAG_RE.sub("", stem)
    cleaned = ROUND_TAG_RE.sub(
        lambda match: "" if is_removable_round_tag(match.group(1)) else match.group(0),
        cleaned,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ._-")
    return sanitize_filename(cleaned or stem)


def sanitize_filename(value: str) -> str:
    value = INVALID_FILENAME_CHARS_RE.sub(" ", value)
    value = re.sub(r"\s+", " ", value).strip(" .")
    return value or "ROM"


def is_region_tag(tag: str) -> bool:
    normalized = normalize_region(tag)
    if normalized in COUNTRY_CODES:
        return True
    return 1 < len(normalized) <= 3 and set(normalized).issubset({"J", "U", "E"})


def is_removable_round_tag(tag: str) -> bool:
    normalized = tag.strip()
    upper = normalized.upper()
    if is_region_tag(normalized):
        return True
    if upper in ROUND_METADATA_TAGS:
        return True
    if REVISION_RE.match(normalized):
        return True
    if re.match(r"^M\d+$", upper):
        return True
    if re.match(r"^V\d+(?:\.\d+)*(?:[A-Z]+)?$", upper):
        return True
    if re.match(r"^\d+\s*(?:K|MBIT)$", upper):
        return True
    if re.match(r"^(?:ALPHA|BETA|PROTOTYPE|DEMO|RC)\b", upper):
        return True
    if re.match(r"^[A-Z]{1,3}-GC$", upper):
        return True
    if re.match(r"^[A-Z]{2}-TRAD$|^[A-Z]{2}-SIMPLE$", upper):
        return True
    return False


def extract_revision(round_tags: list[str]) -> int | None:
    revisions: list[int] = []
    for tag in round_tags:
        match = REVISION_RE.match(tag.strip())
        if match:
            revisions.append(int(match.group(1)))
    return max(revisions) if revisions else None


def extract_languages(square_tags: list[str]) -> list[str]:
    languages: list[str] = []
    for tag in square_tags:
        match = TRANSLATION_RE.match(tag.strip())
        if match:
            languages.append(normalize_language(match.group(1)))
    return languages or ["original"]


def extract_regions(round_tags: list[str]) -> list[str]:
    return [normalize_region(tag) for tag in round_tags if is_region_tag(tag)]


def build_candidate(archive_path: Path, member_name: str) -> RomCandidate:
    filename = strip_archive_path(member_name)
    round_tags = [tag.strip() for tag in ROUND_TAG_RE.findall(filename)]
    square_tags = [tag.strip() for tag in SQUARE_TAG_RE.findall(filename)]
    return RomCandidate(
        archive_path=archive_path,
        member_name=member_name,
        file_extension=Path(filename).suffix.lower(),
        clean_title=clean_game_title(filename),
        round_tags=round_tags,
        square_tags=square_tags,
        regions=extract_regions(round_tags),
        languages=extract_languages(square_tags),
        revision=extract_revision(round_tags),
    )


def build_candidates(archive_path: Path, config: AppConfig) -> list[RomCandidate]:
    candidates = []
    for member_name in list_archive_members(archive_path):
        extension = Path(strip_archive_path(member_name)).suffix.lower()
        if extension not in config.rom_extensions:
            continue
        candidates.append(build_candidate(archive_path, member_name))
    return candidates


def region_matches(wanted: str, actual: str) -> bool:
    wanted = normalize_region(wanted)
    actual = normalize_region(actual)
    if wanted == "*":
        return True
    if wanted == actual:
        return True
    if wanted in {"U", "E", "J"} and set(actual).issubset({"U", "E", "J"}):
        return wanted in actual
    return False


def region_rank(candidate: RomCandidate, priorities: list[str]) -> int:
    if not priorities:
        return 0
    for index, wanted in enumerate(priorities):
        if wanted == "*":
            return index
        if any(region_matches(wanted, actual) for actual in candidate.regions):
            return index
    return len(priorities) + 1


def language_rank(candidate: RomCandidate, priorities: list[str]) -> int:
    if not priorities:
        return 0
    for index, wanted in enumerate(priorities):
        if wanted == "*":
            return index
        if wanted in candidate.languages:
            return index
    return len(priorities) + 1


def quality_prefix_match(tag: str, prefix: str) -> bool:
    if prefix == "!":
        return tag == "!"
    if prefix == "T":
        return tag.startswith("T+") or tag.startswith("T-")
    if prefix == "!p":
        return tag == "!p"
    return tag.lower().startswith(prefix.lower())


def quality_entry_matches(candidate: RomCandidate, entry: str) -> bool:
    normalized = normalize_quality(entry)
    lowered = normalized.lower()
    if lowered in {"unknown", "none", "untagged"}:
        return not candidate.square_tags
    prefixes = QUALITY_ALIASES.get(lowered, [normalized])
    return any(
        quality_prefix_match(tag, prefix)
        for tag in candidate.square_tags
        for prefix in prefixes
    )


def quality_rank(candidate: RomCandidate, priorities: list[str]) -> int:
    if not priorities:
        return 0
    for index, entry in enumerate(priorities):
        if quality_entry_matches(candidate, entry):
            return index
    return len(priorities) + 1


def quality_penalty(candidate: RomCandidate) -> int:
    penalty = 0
    for tag in candidate.square_tags:
        if tag in QUALITY_PENALTY:
            penalty += QUALITY_PENALTY[tag]
            continue
        if tag.startswith("!p"):
            penalty += QUALITY_PENALTY["!p"]
            continue
        if tag.startswith("T+") or tag.startswith("T-"):
            penalty += QUALITY_PENALTY["T"]
            continue
        if tag:
            penalty += QUALITY_PENALTY.get(tag[0], 0)
    return penalty


def revision_rank(candidate: RomCandidate, prefer_revision: str) -> int:
    if prefer_revision == "none" or candidate.revision is None:
        return 0
    if prefer_revision == "oldest":
        return candidate.revision
    return -candidate.revision


def candidate_score(candidate: RomCandidate, config: AppConfig) -> tuple[Any, ...]:
    components = {
        "language": language_rank(candidate, config.language_priority),
        "region": region_rank(candidate, config.region_priority),
        "quality": quality_rank(candidate, config.quality_priority),
        "revision": revision_rank(candidate, config.prefer_revision),
    }
    score: list[Any] = []
    for key in config.selection_order:
        score.append(components[key])
        if key == "quality":
            score.append(quality_penalty(candidate))
    score.append(candidate.clean_title.lower())
    score.append(candidate.member_name.lower())
    return tuple(score)


def select_candidate(
    candidates: list[RomCandidate], config: AppConfig
) -> RomCandidate | None:
    if not candidates:
        return None
    return min(candidates, key=lambda candidate: candidate_score(candidate, config))


def member_output_name(candidate: RomCandidate) -> str:
    return sanitize_filename(candidate.clean_title) + candidate.file_extension


def output_archive_path(
    output_dir: Path,
    candidate: RomCandidate,
    archive_format: str,
    overwrite: bool,
    reserved_paths: set[Path] | None = None,
) -> Path:
    base = sanitize_filename(candidate.clean_title)
    suffix = f".{archive_format}"
    path = output_dir / f"{base}{suffix}"
    if (overwrite or not path.exists()) and (
        reserved_paths is None or path not in reserved_paths
    ):
        return path
    counter = 2
    while True:
        next_path = output_dir / f"{base} ({counter}){suffix}"
        if not next_path.exists() and (
            reserved_paths is None or next_path not in reserved_paths
        ):
            return next_path
        counter += 1


class OutputPathAllocator:
    def __init__(self, output_dir: Path, archive_format: str, overwrite: bool) -> None:
        self._output_dir = output_dir
        self._archive_format = archive_format
        self._overwrite = overwrite
        self._reserved_paths: set[Path] = set()
        self._lock = threading.Lock()

    def __call__(self, candidate: RomCandidate) -> Path:
        with self._lock:
            path = output_archive_path(
                self._output_dir,
                candidate,
                self._archive_format,
                self._overwrite,
                self._reserved_paths,
            )
            self._reserved_paths.add(path)
            return path


def member_extract_path(root: Path, member_name: str) -> Path:
    parts = [part for part in re.split(r"[\\/]+", member_name) if part]
    target = root.joinpath(*parts).resolve()
    root_resolved = root.resolve()
    if target != root_resolved and root_resolved not in target.parents:
        raise RuntimeError(f"Archive member escapes extraction directory: {member_name}")
    return target


def extract_member(archive_path: Path, member_name: str, target_file: Path) -> None:
    suffix = archive_path.suffix.lower()
    target_file.parent.mkdir(parents=True, exist_ok=True)
    if suffix == ".zip":
        with zipfile.ZipFile(archive_path, "r") as archive:
            target_file.write_bytes(archive.read(member_name))
        return
    if suffix == ".7z":
        try:
            import py7zr
        except ImportError as exc:
            raise RuntimeError(
                "py7zr is required to extract .7z archives. Install it with: pip install py7zr"
            ) from exc
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            with py7zr.SevenZipFile(archive_path, "r") as archive:
                archive.extract(path=temp_path, targets=[member_name])
            extracted = member_extract_path(temp_path, member_name)
            if not extracted.exists():
                matches = list(temp_path.rglob(strip_archive_path(member_name)))
                if not matches:
                    raise RuntimeError(f"Cannot find extracted member: {member_name}")
                extracted = matches[0]
            shutil.move(str(extracted), target_file)
        return
    raise RuntimeError(f"Unsupported archive type: {archive_path}")


def create_output_archive(
    source_file: Path, output_archive: Path, arcname: str, archive_format: str
) -> None:
    output_archive.parent.mkdir(parents=True, exist_ok=True)
    if archive_format == "zip":
        with zipfile.ZipFile(
            output_archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as archive:
            archive.write(source_file, arcname)
        return
    if archive_format == "7z":
        try:
            import py7zr
        except ImportError as exc:
            raise RuntimeError(
                "py7zr is required to write .7z archives. Install it with: pip install py7zr"
            ) from exc
        with py7zr.SevenZipFile(output_archive, "w") as archive:
            archive.write(source_file, arcname)
        return
    raise RuntimeError(f"Unsupported output format: {archive_format}")


def process_archive(
    archive_path: Path,
    config: AppConfig,
    output_path_allocator: Callable[[RomCandidate], Path] | None = None,
) -> ProcessResult:
    try:
        candidates = build_candidates(archive_path, config)
        selected = select_candidate(candidates, config)
        if selected is None:
            return ProcessResult(archive_path, None, None, "no ROM candidates")

        if output_path_allocator is None:
            output_path = output_archive_path(
                config.output_dir, selected, config.archive_format, config.overwrite
            )
        else:
            output_path = output_path_allocator(selected)
        if config.dry_run:
            return ProcessResult(archive_path, selected, output_path, "dry run")

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_rom = Path(temp_dir) / member_output_name(selected)
            extract_member(archive_path, selected.member_name, temp_rom)
            create_output_archive(
                temp_rom,
                output_path,
                member_output_name(selected),
                config.archive_format,
            )
        return ProcessResult(archive_path, selected, output_path, "ok")
    except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
        return ProcessResult(archive_path, None, None, f"error: {exc}")


def print_config(config: AppConfig) -> None:
    print(f"Input: {config.input_dir}")
    print(f"Output: {config.output_dir}")
    print(f"Output format: {config.archive_format}")
    print(f"Language priority: {', '.join(config.language_priority)}")
    print(f"Quality priority: {', '.join(config.quality_priority)}")
    print(f"Region priority: {', '.join(config.region_priority)}")
    print(f"Selection order: {', '.join(config.selection_order)}")
    print(f"Workers: {config.workers}")


def print_result(result: ProcessResult) -> None:
    archive_name = result.archive_path.name
    if result.selected is None:
        print(f"SKIP  {archive_name}: {result.reason}")
        return
    output_name = result.output_path.name if result.output_path else "<none>"
    print(f"OK    {archive_name}: {result.selected.member_name} -> {output_name}")


def print_progress(current: int, total: int, archive_path: Path) -> None:
    percent = (current / total * 100) if total else 100.0
    width = len(str(total))
    print(f"[{current:>{width}}/{total} {percent:6.2f}%] {archive_path.name}")


def run(config: AppConfig) -> int:
    if not config.input_dir.exists():
        print(f"Input directory does not exist: {config.input_dir}", file=sys.stderr)
        return 1
    if not config.input_dir.is_dir():
        print(f"Input path is not a directory: {config.input_dir}", file=sys.stderr)
        return 1
    if not config.dry_run:
        config.output_dir.mkdir(parents=True, exist_ok=True)

    print_config(config)
    archives = find_archives(config.input_dir, config.recursive)
    if not archives:
        print("No .zip or .7z archives found.")
        return 0

    total = len(archives)
    if config.workers == 1:
        results = process_archives_sequentially(archives, config)
    else:
        results = process_archives_in_parallel(archives, config)

    ok = sum(1 for result in results if result.selected is not None)
    skipped = len(results) - ok
    errors = sum(1 for result in results if result.reason.startswith("error:"))
    print(f"Done. Selected: {ok}. Skipped: {skipped}. Errors: {errors}.")
    return 1 if errors else 0


def process_archives_sequentially(
    archives: list[Path], config: AppConfig
) -> list[ProcessResult]:
    results = []
    total = len(archives)
    for index, archive in enumerate(archives, start=1):
        print_progress(index, total, archive)
        result = process_archive(archive, config)
        results.append(result)
        print_result(result)
    return results


def process_archives_in_parallel(
    archives: list[Path], config: AppConfig
) -> list[ProcessResult]:
    results = []
    total = len(archives)
    allocator = OutputPathAllocator(
        config.output_dir, config.archive_format, config.overwrite
    )
    with ThreadPoolExecutor(max_workers=config.workers) as executor:
        future_to_archive = {
            executor.submit(process_archive, archive, config, allocator): archive
            for archive in archives
        }
        for index, future in enumerate(as_completed(future_to_archive), start=1):
            archive = future_to_archive[future]
            print_progress(index, total, archive)
            try:
                result = future.result()
            except Exception as exc:
                result = ProcessResult(archive, None, None, f"error: {exc}")
            results.append(result)
            print_result(result)
    return results


def main(argv: list[str] | None = None) -> int:
    parser = create_arg_parser()
    args = parser.parse_args(argv)
    config = build_config(args)
    return run(config)


if __name__ == "__main__":
    sys.exit(main())
