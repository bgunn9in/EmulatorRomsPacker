#!/usr/bin/env python
import asyncio
# coding: utf-8

import os
import shutil
import zipfile


async def zip_file(output_path: str, input_path: str, item: str) -> None:
    with zipfile.ZipFile(output_path, mode='w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        print(f'Processing: {item} ...')
        archive.write(input_path, item)


async def main() -> None:
    roms: str = '/Users/bengunn/Documents/smd_roms'
    output: str = '/Users/bengunn/Documents/processed_smd_roms'

    if not os.path.exists(roms):
        print(f'Roms dir: {roms} not exists, aborting!')
        return
    if not os.path.exists(output):
        print(f'Output dir: {output} not exists, creating!')
        os.mkdir(output)
    else:
        print(f'Output dir exists! Clean up!')
        shutil.rmtree(output)
        os.mkdir(output)

    tasks: list = []
    for item in os.listdir(roms):
        item_no_ext: str = os.path.splitext(item)[0]
        input_path: str = os.path.join(roms, item)
        output_path: str = os.path.join(output, f'{item_no_ext}.zip')
        tasks.append(asyncio.create_task(zip_file(output_path, input_path, item)))

    await asyncio.gather(*tasks)


if __name__ == '__main__':
    asyncio.run(main())
