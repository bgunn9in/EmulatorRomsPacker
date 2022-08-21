#!/usr/bin/env python
import logging
# coding: utf-8

import re


class DuplicateFinder:
    def __int__(self):
        logging.basicConfig(format='%(asctime)s %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p', filename='main.log', encoding='utf-8', level=logging.DEBUG)
        pass

    @staticmethod
    def __filter(region_data: str) -> bool:
        regions: list = ['(U)', '(E)', '(UE)', '(W)', ]
        for region in regions:
            if region in region_data:
                return False
        return True

    def __regex_finder(self, file: str, files: list) -> list:
        regex_list: list = [
            re.compile(r'\s+\(.*\).*\[.*\]', re.IGNORECASE),
            re.compile(r'\s+\(.*\).*\[.*\)', re.IGNORECASE),
            re.compile(r'\s+\(.*\)', re.IGNORECASE),
        ]
        clean_data: list = []
        for regex in regex_list:
            result: list = regex.findall(file)
            if len(result) == 0:
                logging.warning(f'Can\'t get regex, result: {file}')
                continue
            name: list = file.split(result[0])
            if len(name) < 2:
                logging.warning(f'Can\'t get game name, result: {name}')
                continue
            if self.__filter(result[0]):
                logging.info(f'Skip file {file} by filter')
                continue
            clean_data.append(f'{name[0]} {result[0]} {name[1]}')
        return clean_data

    def find(self, files: list) -> list:
        for file in files:
            self.__regex_finder(file, files)
        return []


duplicate_finder: DuplicateFinder = DuplicateFinder()
