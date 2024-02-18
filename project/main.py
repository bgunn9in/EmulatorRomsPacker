#!/usr/bin/env python

# coding: utf-8

import argparse
from dataclasses import dataclass
import os
import sys


@dataclass
class Args:
    input: str = ""
    output: str = ""
    region: str = ""
    language: str = ""


@dataclass
class Archives:
    zip: list[str] = []
    z7: list[str] = []


def parse_args() -> Args:
    parser = argparse.ArgumentParser(
        description="Extract ROMs by region from ZIP archives."
    )
    parser.add_argument(
        "-i",
        "--input",
        required=True,
        type=str,
        help="Path to the directory containing ZIP archives.",
    )
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        type=str,
        help="Path to the directory containing extracted ZIP archives.",
    )
    parser.add_argument(
        "-r",
        "--region",
        required=True,
        type=str,
        help="Region name (case-insensitive).",
    )
    parser.add_argument(
        "-l",
        "--language",
        required=False,
        type=str,
        help="Translate language (case-insensitive).",
    )
    args = parser.parse_args()
    return Args(
        os.path.normcase(os.path.normpath(args.input)).strip(),
        os.path.normcase(os.path.normpath(args.output)).strip(),
        args.region.strip(),
        str(args.language).strip(),
    )


def check_input_output(input_dir: str, output_dir: str) -> bool:
    if not os.path.exists(input_dir):
        print(f"Input path not exists: {input_dir}. Exit.")
        return False
    if not os.path.exists(output_dir):
        print(f"Output path not exists: {output_dir}. Try create.")
        try:
            os.makedirs(output_dir)
            print(f"Output directory created: {output_dir}.")
            return True
        except OSError as e:
            print(f"Can't create output directory: {output_dir}, because {e}. Exit.")
            return False
    return True


def find_zip_files(input_dir: str) -> Archives:
    data: Archives = Archives()
    for f in os.listdir(input):
        path: str = os.path.normcase(os.path.normpath(os.path.join(input_dir, f)))
        if path.endswith(".zip"):
            data.zip.append(path)
        elif path.endswith(".7z"):
            data.zip.append(path)
    return data


def process_zip(zips: list[str]) -> None:
    pass


def process_7z(z7zs: list[str]) -> None:
    pass


def main() -> int:
    args: Args = parse_args()
    if not check_input_output(args.input, args.output):
        return 1
    archives: Archives = find_zip_files(args.input)
    if not archives:
        print(f"No input files found in: {args.input}. Exit.")
        return 0

    process_zip(archives.zip)
    process_7z(archives.z7)


if __name__ == "__main__":
    sys.exit(main())
