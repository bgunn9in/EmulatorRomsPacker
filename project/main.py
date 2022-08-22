#!/usr/bin/env python

# coding: utf-8

import os
import shutil
import zipfile
import asyncio

from project.ConfigKeeper import config_keeper
from project.DuplicateFinder import duplicate_finder


async def zip_file(output_path: str, input_path: str, item: str) -> None:
    with zipfile.ZipFile(output_path, mode='w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        print(f'Processing: {item} ...')
        archive.write(input_path, item)


def check_dirs(roms_dir: str, output_dir: str) -> None:
    if not os.path.exists(roms_dir):
        print(f'Roms dir: {roms_dir} not exists, aborting!')
        return
    if not os.path.exists(output_dir):
        print(f'Output dir: {output_dir} not exists, creating!')
        os.mkdir(output_dir)
    else:
        print(f'Output dir exists! Clean up!')
        shutil.rmtree(output_dir)
        os.mkdir(output_dir)


async def main() -> None:
    check_dirs(config_keeper.roms_dir, config_keeper.output_dir)
    rom_files: list = os.listdir(config_keeper.roms_dir)
    cleaned_rom_files = duplicate_finder.exclude(rom_files)

    tasks: list = []
    for item in cleaned_rom_files:
        item_no_ext: str = os.path.splitext(item)[0]
        input_path: str = os.path.join(config_keeper.roms_dir, item)
        output_path: str = os.path.join(config_keeper.output_dir, f'{item_no_ext}.zip')
        tasks.append(asyncio.create_task(zip_file(output_path, input_path, item)))

    await asyncio.gather(*tasks)


if __name__ == '__main__':
    asyncio.run(main())
