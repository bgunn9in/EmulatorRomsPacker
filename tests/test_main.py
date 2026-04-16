import importlib.util
import json
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from main import (
    AppConfig,
    DEFAULT_QUALITY_PRIORITY,
    build_candidate,
    build_config,
    create_arg_parser,
    clean_game_title,
    find_archives,
    normalize_extension,
    normalize_language,
    normalize_region,
    output_archive_path,
    parse_csv,
    print_progress,
    process_archive,
    run,
    select_candidate,
)


def make_config(**overrides):
    values = {
        "input_dir": Path("."),
        "output_dir": Path("."),
        "archive_format": "zip",
        "region_priority": ["U", "E", "W", "J"],
        "language_priority": ["original"],
        "quality_priority": DEFAULT_QUALITY_PRIORITY.copy(),
        "selection_order": ["language", "quality", "region", "revision"],
        "rom_extensions": {".bin"},
        "recursive": False,
        "overwrite": False,
        "dry_run": False,
        "prefer_revision": "newest",
        "workers": 1,
        "log_file": None,
    }
    values.update(overrides)
    return AppConfig(**values)


class SelectionTests(unittest.TestCase):
    def test_parse_csv_accepts_strings_and_iterables(self):
        self.assertEqual(parse_csv("U, E,,W"), ["U", "E", "W"])
        self.assertEqual(parse_csv(["Rus,Eng", "original"]), ["Rus", "Eng", "original"])
        self.assertEqual(parse_csv(None), [])

    def test_normalizers_accept_common_aliases(self):
        self.assertEqual(normalize_region("usa"), "U")
        self.assertEqual(normalize_region("Europe"), "E")
        self.assertEqual(normalize_region("any"), "*")
        self.assertEqual(normalize_language("Orig"), "original")
        self.assertEqual(normalize_extension("BIN"), ".bin")

    def test_clean_title_removes_goodtools_tags(self):
        self.assertEqual(
            clean_game_title("Sonic The Hedgehog (W) (REV01) [!].bin"),
            "Sonic The Hedgehog",
        )

    def test_clean_title_keeps_unknown_parenthetical_title_text(self):
        self.assertEqual(
            clean_game_title("Xin Qi Gai Wang Zi (Prince and the Pauper) (Ch).bin"),
            "Xin Qi Gai Wang Zi (Prince and the Pauper)",
        )

    def test_build_candidate_extracts_tags(self):
        candidate = build_candidate(
            Path("Game.7z"),
            "nested/Game Name (UE) (REV02) [T+Rus_Team][!].bin",
        )

        self.assertEqual(candidate.clean_title, "Game Name")
        self.assertEqual(candidate.file_extension, ".bin")
        self.assertEqual(candidate.regions, ["UE"])
        self.assertEqual(candidate.languages, ["rus"])
        self.assertEqual(candidate.revision, 2)
        self.assertEqual(candidate.square_tags, ["T+Rus_Team", "!"])

    def test_quality_wins_before_region_by_default(self):
        archive = Path("Game.7z")
        candidates = [
            build_candidate(archive, "Game (U) [b1].bin"),
            build_candidate(archive, "Game (E) [!].bin"),
        ]
        selected = select_candidate(candidates, make_config())
        self.assertEqual(selected.member_name, "Game (E) [!].bin")

    def test_region_first_order_can_choose_region_before_quality(self):
        archive = Path("Game.7z")
        candidates = [
            build_candidate(archive, "Game (U) [b1].bin"),
            build_candidate(archive, "Game (E) [!].bin"),
        ]
        selected = select_candidate(
            candidates,
            make_config(selection_order=["language", "region", "quality", "revision"]),
        )
        self.assertEqual(selected.member_name, "Game (U) [b1].bin")

    def test_region_priority_falls_back_to_europe_when_usa_missing(self):
        archive = Path("Game.7z")
        candidates = [
            build_candidate(archive, "Game (J) [!].bin"),
            build_candidate(archive, "Game (E) [!].bin"),
        ]
        selected = select_candidate(candidates, make_config())
        self.assertEqual(selected.member_name, "Game (E) [!].bin")

    def test_compound_region_matches_single_region_priority(self):
        archive = Path("Game.7z")
        candidates = [
            build_candidate(archive, "Game (J) [!].bin"),
            build_candidate(archive, "Game (UE) [!].bin"),
        ]
        selected = select_candidate(candidates, make_config(region_priority=["U", "J"]))
        self.assertEqual(selected.member_name, "Game (UE) [!].bin")

    def test_language_priority_selects_translation(self):
        archive = Path("Game.7z")
        candidates = [
            build_candidate(archive, "Game (U) [!].bin"),
            build_candidate(archive, "Game (U) [T+Rus_Team].bin"),
        ]
        selected = select_candidate(
            candidates,
            make_config(language_priority=["rus", "original"]),
        )
        self.assertEqual(selected.member_name, "Game (U) [T+Rus_Team].bin")

    def test_original_fallback_when_requested_translation_is_missing(self):
        archive = Path("Game.7z")
        candidates = [
            build_candidate(archive, "Game (U) [!].bin"),
            build_candidate(archive, "Game (U) [T+Fre_Team].bin"),
        ]
        selected = select_candidate(
            candidates,
            make_config(language_priority=["rus", "original"]),
        )
        self.assertEqual(selected.member_name, "Game (U) [!].bin")

    def test_unknown_quality_can_be_prioritized(self):
        archive = Path("Game.7z")
        candidates = [
            build_candidate(archive, "Game (U) [!].bin"),
            build_candidate(archive, "Game (U).bin"),
        ]
        selected = select_candidate(
            candidates,
            make_config(quality_priority=["unknown", "verified"]),
        )
        self.assertEqual(selected.member_name, "Game (U).bin")

    def test_quality_penalty_prefers_clean_verified_over_pirate_verified(self):
        archive = Path("Game.7z")
        candidates = [
            build_candidate(archive, "Game (U) [p1][!].bin"),
            build_candidate(archive, "Game (U) [!].bin"),
        ]
        selected = select_candidate(candidates, make_config())
        self.assertEqual(selected.member_name, "Game (U) [!].bin")

    def test_newest_revision_wins_tie(self):
        archive = Path("Game.7z")
        candidates = [
            build_candidate(archive, "Game (U) (REV00) [!].bin"),
            build_candidate(archive, "Game (U) (REV01) [!].bin"),
        ]
        selected = select_candidate(candidates, make_config())
        self.assertEqual(selected.member_name, "Game (U) (REV01) [!].bin")

    def test_oldest_revision_can_win_tie(self):
        archive = Path("Game.7z")
        candidates = [
            build_candidate(archive, "Game (U) (REV00) [!].bin"),
            build_candidate(archive, "Game (U) (REV01) [!].bin"),
        ]
        selected = select_candidate(
            candidates,
            make_config(prefer_revision="oldest"),
        )
        self.assertEqual(selected.member_name, "Game (U) (REV00) [!].bin")


class ProcessingTests(unittest.TestCase):
    def test_process_zip_archive_repacks_selected_rom(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_archive = root / "Game.zip"
            output_dir = root / "output"
            with zipfile.ZipFile(input_archive, "w") as archive:
                archive.writestr("Game (U) [b1].bin", b"bad")
                archive.writestr("Game (E) [!].bin", b"good")

            result = process_archive(
                input_archive,
                make_config(output_dir=output_dir),
            )

            self.assertEqual(result.reason, "ok")
            self.assertEqual(result.selected.member_name, "Game (E) [!].bin")
            self.assertTrue(result.output_path.exists())
            with zipfile.ZipFile(result.output_path, "r") as archive:
                self.assertEqual(archive.namelist(), ["Game.bin"])
                self.assertEqual(archive.read("Game.bin"), b"good")

    def test_process_zip_archive_skips_when_no_rom_extensions_match(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_archive = root / "Game.zip"
            with zipfile.ZipFile(input_archive, "w") as archive:
                archive.writestr("readme.txt", b"not a rom")

            result = process_archive(input_archive, make_config(output_dir=root / "out"))

            self.assertIsNone(result.selected)
            self.assertEqual(result.reason, "no ROM candidates")

    def test_process_zip_dry_run_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_archive = root / "Game.zip"
            output_dir = root / "output"
            with zipfile.ZipFile(input_archive, "w") as archive:
                archive.writestr("Game (U) [!].bin", b"rom")

            result = process_archive(
                input_archive,
                make_config(output_dir=output_dir, dry_run=True),
            )

            self.assertEqual(result.reason, "dry run")
            self.assertEqual(result.output_path, output_dir / "Game.zip")
            self.assertFalse(result.output_path.exists())

    def test_output_archive_path_adds_suffix_when_file_exists(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            candidate = build_candidate(Path("Game.zip"), "Game (U) [!].bin")
            (output_dir / "Game.zip").write_bytes(b"existing")

            path = output_archive_path(output_dir, candidate, "zip", overwrite=False)

            self.assertEqual(path, output_dir / "Game (2).zip")

    def test_output_archive_path_uses_same_name_when_overwrite_enabled(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            candidate = build_candidate(Path("Game.zip"), "Game (U) [!].bin")
            (output_dir / "Game.zip").write_bytes(b"existing")

            path = output_archive_path(output_dir, candidate, "zip", overwrite=True)

            self.assertEqual(path, output_dir / "Game.zip")

    def test_find_archives_respects_recursive_flag(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            nested = root / "nested"
            nested.mkdir()
            (root / "top.zip").write_bytes(b"")
            (nested / "nested.7z").write_bytes(b"")
            (root / "ignore.txt").write_bytes(b"")

            self.assertEqual(find_archives(root, recursive=False), [root / "top.zip"])
            self.assertEqual(
                find_archives(root, recursive=True),
                sorted([root / "top.zip", nested / "nested.7z"]),
            )

    def test_print_progress_includes_counter_percent_and_archive_name(self):
        output = StringIO()

        with redirect_stdout(output):
            print_progress(2, 10, Path("Game.7z"))

        self.assertEqual(output.getvalue(), "[ 2/10  20.00%] Game.7z\n")

    @unittest.skipIf(importlib.util.find_spec("py7zr") is None, "py7zr is not installed")
    def test_process_7z_archive_repacks_selected_rom_as_zip(self):
        import py7zr

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            staging = root / "staging"
            staging.mkdir()
            (staging / "Game (U) [b1].bin").write_bytes(b"bad")
            (staging / "Game (E) [!].bin").write_bytes(b"good")
            input_archive = root / "Game.7z"
            output_dir = root / "output"
            with py7zr.SevenZipFile(input_archive, "w") as archive:
                archive.write(staging / "Game (U) [b1].bin", "Game (U) [b1].bin")
                archive.write(staging / "Game (E) [!].bin", "Game (E) [!].bin")

            result = process_archive(
                input_archive,
                make_config(output_dir=output_dir, archive_format="zip"),
            )

            self.assertEqual(result.reason, "ok")
            self.assertEqual(result.selected.member_name, "Game (E) [!].bin")
            with zipfile.ZipFile(result.output_path, "r") as archive:
                self.assertEqual(archive.namelist(), ["Game.bin"])
                self.assertEqual(archive.read("Game.bin"), b"good")


class ConfigTests(unittest.TestCase):
    def test_build_config_uses_json_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "input_dir": "roms",
                        "output_dir": "packed",
                        "archive_format": "zip",
                        "region_priority": ["Europe", "USA"],
                        "language_priority": ["Rus"],
                        "quality_priority": ["bad", "verified"],
                        "selection_order": ["region", "quality"],
                        "rom_extensions": ["bin", ".smd"],
                        "recursive": True,
                        "overwrite": True,
                        "dry_run": True,
                        "prefer_revision": "oldest",
                        "workers": 3,
                        "log_file": "logs/events.jsonl",
                    }
                ),
                encoding="utf-8",
            )

            args = create_arg_parser().parse_args(["--config", str(config_path)])
            config = build_config(args)

            self.assertEqual(config.input_dir, Path("roms"))
            self.assertEqual(config.output_dir, Path("packed"))
            self.assertEqual(config.archive_format, "zip")
            self.assertEqual(config.region_priority, ["E", "U"])
            self.assertEqual(config.language_priority, ["rus"])
            self.assertEqual(config.quality_priority, ["bad", "verified"])
            self.assertEqual(config.selection_order, ["region", "quality"])
            self.assertEqual(config.rom_extensions, {".bin", ".smd"})
            self.assertTrue(config.recursive)
            self.assertTrue(config.overwrite)
            self.assertTrue(config.dry_run)
            self.assertEqual(config.prefer_revision, "oldest")
            self.assertEqual(config.workers, 3)
            self.assertEqual(config.log_file, Path("logs/events.jsonl"))

    def test_build_config_cli_overrides_json_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "input_dir": "json-input",
                        "output_dir": "json-output",
                        "archive_format": "7z",
                        "region_priority": ["J"],
                        "language_priority": ["Fre"],
                        "quality_priority": ["bad"],
                        "recursive": True,
                    }
                ),
                encoding="utf-8",
            )

            args = create_arg_parser().parse_args(
                [
                    "--config",
                    str(config_path),
                    "-i",
                    "cli-input",
                    "-o",
                    "cli-output",
                    "--format",
                    "zip",
                    "--regions",
                    "U,E",
                    "--languages",
                    "Rus",
                    "--qualities",
                    "verified",
                    "--no-recursive",
                    "--workers",
                    "2",
                    "--log-file",
                    "cli-log.jsonl",
                ]
            )
            config = build_config(args)

            self.assertEqual(config.input_dir, Path("cli-input"))
            self.assertEqual(config.output_dir, Path("cli-output"))
            self.assertEqual(config.archive_format, "zip")
            self.assertEqual(config.region_priority, ["U", "E"])
            self.assertEqual(config.language_priority, ["rus", "original"])
            self.assertEqual(config.quality_priority, ["verified"])
            self.assertFalse(config.recursive)
            self.assertEqual(config.workers, 2)
            self.assertEqual(config.log_file, Path("cli-log.jsonl"))

    def test_build_config_rejects_unknown_selection_key(self):
        args = create_arg_parser().parse_args(["--selection-order", "region,size"])

        with self.assertRaises(SystemExit):
            build_config(args)

    def test_build_config_rejects_invalid_json_shape(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text("[]", encoding="utf-8")
            args = create_arg_parser().parse_args(["--config", str(config_path)])

            with self.assertRaises(SystemExit):
                build_config(args)

    def test_build_config_rejects_invalid_workers(self):
        args = create_arg_parser().parse_args(["--workers", "0"])

        with self.assertRaises(SystemExit):
            build_config(args)

    def test_run_can_process_archives_in_parallel(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_dir = root / "input"
            output_dir = root / "output"
            input_dir.mkdir()
            for name in ["One", "Two"]:
                with zipfile.ZipFile(input_dir / f"{name}.zip", "w") as archive:
                    archive.writestr(f"{name} (U) [!].bin", name.encode("ascii"))

            output = StringIO()
            with redirect_stdout(output):
                exit_code = run(
                    make_config(
                        input_dir=input_dir,
                        output_dir=output_dir,
                        dry_run=True,
                        workers=2,
                    )
                )

            self.assertEqual(exit_code, 0)
            self.assertIn("Workers: 2", output.getvalue())
            self.assertIn("Done. Selected: 2. Skipped: 0. Errors: 0.", output.getvalue())

    def test_run_logs_skipped_archives_and_errors(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_dir = root / "input"
            output_dir = root / "output"
            log_file = root / "logs" / "events.jsonl"
            input_dir.mkdir()
            with zipfile.ZipFile(input_dir / "NoRom.zip", "w") as archive:
                archive.writestr("readme.txt", b"not a rom")
            (input_dir / "Broken.zip").write_bytes(b"not a zip")

            output = StringIO()
            with redirect_stdout(output):
                exit_code = run(
                    make_config(
                        input_dir=input_dir,
                        output_dir=output_dir,
                        log_file=log_file,
                    )
                )

            self.assertEqual(exit_code, 1)
            records = [
                json.loads(line)
                for line in log_file.read_text(encoding="utf-8").splitlines()
            ]
            events = {record["event"] for record in records}
            reasons = {record["reason"] for record in records}
            self.assertEqual(events, {"skipped", "error"})
            self.assertIn("no ROM candidates", reasons)
            self.assertTrue(any(reason.startswith("error:") for reason in reasons))
            self.assertTrue(all("member_count" in record for record in records))
            self.assertTrue(all("candidate_count" in record for record in records))


if __name__ == "__main__":
    unittest.main()
