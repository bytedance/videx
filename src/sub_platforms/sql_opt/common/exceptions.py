"""
Copyright (c) 2024 Bytedance Ltd. and/or its affiliates
SPDX-License-Identifier: MIT

@ author: bytebrain
@ date: 2025-03-13

"""
class RequestFormatException(Exception):
    """
        输入的优化任务信息不全，格式错误等
    """

    def __init__(self, message):
        self.message = message
        super().__init__(self.message)

    def __str__(self):
        return f"Optimize task format Exception: {self.message}"


class TableNotFoundException(Exception):
    def __init__(self, message, table_name):
        self.message = message
        self.table_name = table_name
        super().__init__(self.message)

    def __str__(self):
        return f"Table not found Exception: {self.message}, table : {self.table_name}"


class UnsupportedException(Exception):
    def __init__(self, message):
        super(UnsupportedException, self).__init__(message)


class UnsupportedQueryException(UnsupportedException):
    def __init__(self, message, fingerprint_md5, sample_sql):
        self.message = message
        self.fingerprint_md5 = fingerprint_md5
        self.sample_sql = sample_sql
        super().__init__(self.message)

    def __str__(self):
        return f"Unsupported Query Exception: {self.message}, finger: {self.fingerprint_md5}, sql text: {self.sample_sql}"


class UnsupportedSamplingException(UnsupportedException):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)

    def __str__(self):
        return f"Unsupported sampling Exception: {self.message}"


class UnsupportedParseEngine(UnsupportedException):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)

    def __str__(self):
        return f"Unsupported Parse Engine Exception: {self.message}"


class TraceLoadException(ValueError):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)

    def __str__(self):
        return f"Failed load trace from OPTIMIZE_TRACE"


class LexDictLoadException(ValueError):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)

    def __str__(self):
        return f"Failed load Lex Dict from TRACE"


class CollationQueryException(ValueError):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)

    def __str__(self):
        return f"Failed Query ASCII Collation Weight: {self.message}"


class CollationGenerateStrException(ValueError):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)

    def __str__(self):
        return f"Failed Generated String: {self.message}"


class GenerateNumException(ValueError):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)

    def __str__(self):
        return f"Failed Generated Numeric: {self.message}"
