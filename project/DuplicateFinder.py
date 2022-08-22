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

    @staticmethod
    def __region_filter(region_data: str) -> bool:
        regions: list = ['(U)', '(E)', '(UE)', '(W)', ]
        for region in regions:
            if region in region_data:
                return False
        return True

    def __extract_details(self, regex: iter, file: str, files: list) -> str:
        result: list = next(regex).findall(file)
        if len(result) == 0:
            return self.__extract_details(regex, file, files)
        if self.__region_filter(file):
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
