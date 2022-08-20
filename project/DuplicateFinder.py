#!/usr/bin/env python

# coding: utf-8

import re


class DuplicateFinder:
    def __int__(self):
        pass

    def __regex_finder(self, data: str) -> str:
        pattern = re.compile(r'\s+\(.*\).*\[.*\]', re.IGNORECASE)
        result: list = pattern.findall(data)
        if len(result) == 0:
            pattern = re.compile(r'\s+\(.*\).*\[.*\)', re.IGNORECASE)
            result: list = pattern.findall(data)
            if len(result) == 0:
                pattern = re.compile(r'\s+\(.*\)', re.IGNORECASE)
                result: list = pattern.findall(data)
                if len(result) == 0:
                    b = 1

        return result[0]

    def find(self, files: list) -> list:
        for file in files:
            self.__regex_finder(file)
        return []


duplicate_finder: DuplicateFinder = DuplicateFinder()
