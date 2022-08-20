#!/usr/bin/env python

# coding: utf-8

import re


class DuplicateFinder:
    def __int__(self):
        pass

    def __regex_finder(self, data: str) -> str:
        pattern = re.compile(r'\(.*\).*\[.*\]', re.IGNORECASE)
        return pattern.findall(data)[0]

    def find(self, files: list) -> list:
        for file in files:
            self.__regex_finder(file)
        return []


duplicate_finder: DuplicateFinder = DuplicateFinder()
