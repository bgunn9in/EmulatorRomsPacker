#!/usr/bin/env python

# coding: utf-8

import json
import os


class ConfigKeeper:
    def __init__(self) -> None:
        self.__root_dir: str = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
        self.__config_file: str = os.path.join(self.root_dir, 'config.json')
        self.__load_config()

    def __config_roms_dir(self, data: dict) -> bool:
        if 'roms_dir' not in data:
            print('Config key \'roms_dir\' not found.')
            return False
        self.__roms_dir: str = data['roms_dir']
        return True

    def __config_output_dir(self, data: dict) -> bool:
        if 'output_dir' not in data:
            print('Config key \'output_dir\' not found.')
            return False
        self.__output_dir: str = data['output_dir']
        return True

    def __parse_config(self, data: dict) -> bool:
        print('Reading config...')
        for cr in [self.__config_roms_dir, self.__config_output_dir]:
            if not cr(data):
                return False
        print('Config ok.')
        return True

    def __load_config(self) -> bool:
        with open(self.config_file, 'r', encoding='utf-8') as f:
            return self.__parse_config(json.load(f))

    @property
    def config_file(self) -> str:
        return self.__config_file

    @property
    def root_dir(self) -> str:
        return self.__root_dir

    @property
    def roms_dir(self) -> str:
        return self.__roms_dir

    @property
    def output_dir(self) -> str:
        return self.__output_dir


config_keeper: ConfigKeeper = ConfigKeeper()
