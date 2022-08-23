#!/usr/bin/env python

# coding: utf-8

import re


class DuplicateFinder:
    def __init__(self):
        self.__regex_list: list = [
            re.compile(r'\s+\(.*\).*\[.*\]', re.IGNORECASE),
            re.compile(r'\s+\(.*\).*\[.*\)', re.IGNORECASE),
            re.compile(r'\s+\(.*\)', re.IGNORECASE),
        ]
        self.__regions: list = ['(U)', '(E)', '(UE)', '(W)', ]

    @staticmethod
    def __region_filter(region: iter, region_data: str) -> bool:
        try:
            r: str = next(region)
        except StopIteration:
            return True

        if r in region_data:
            return False
        return DuplicateFinder.__region_filter(region, region_data)

    def __extract_details(self, regex: iter, file: str, files: list) -> str:
        try:
            result: list = next(regex).findall(file)
        except StopIteration:
            return ''

        if len(result) == 0:
            return self.__extract_details(regex, file, files)
        if self.__region_filter(iter(self.__regions), file):
            return ''
        return file

    def __finder(self, file: str, files: list) -> str:
        return self.__extract_details(iter(self.__regex_list), file, files)

    def exclude(self, files: list) -> list:
        duplicates: list = []
        for file in files:
            result: str = self.__finder(file, files)
            if not result:
                continue
            duplicates.append(result)
        return duplicates


duplicate_finder: DuplicateFinder = DuplicateFinder()
