#!/usr/bin/env python3

from __future__ import annotations

import glob
import io
import itertools
import os
import re
import tokenize
from abc import ABC
from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path
from tokenize import TokenInfo
from typing import Union

TokenType = int


class TokenSequence:
    def __init__(self, tokens: list[TokenInfo], token_indexes: list[int], sentinel_token: TokenInfo):
        self.tokens = tokens
        self.token_indexes = token_indexes
        self.sentinel_token = sentinel_token
        self.cursor = 0

    def __getitem__(self, offset: int) -> TokenInfo:
        at = self.cursor + offset
        if at < 0:
            return self.sentinel_token
        elif at >= len(self.token_indexes):
            return self.sentinel_token
        else:
            return self.tokens[self.token_indexes[at]]


class SourceFile:
    def __init__(self, file: str):
        self.file: str = file

        with io.open(file, "r") as fp:
            self.lines: list[str] = [line[:-1] for line in fp.readlines()]

        with io.open(file, "rb") as fp:
            self.tokens: list[TokenInfo] = [t for t in tokenize.tokenize(fp.readline)]

        self.sentinel_token: TokenInfo = self.tokens[0]
        assert self.sentinel_token.type == tokenize.ENCODING

        self.tokens_by_line: defaultdict[int, list[TokenInfo]] = defaultdict(list)
        for token in self.tokens:
            for line in range(token.start[0], token.end[0] + 1):
                self.tokens_by_line[line].append(token)


class Checker:
    def __init__(self, rule_name: str, srcfile: SourceFile, ignore_comments: bool):
        self._rule_name: str = rule_name
        self._srcfile: SourceFile = srcfile
        self._matcher_list_list: list[list[Matcher]] = []
        self._ignore_comments: bool = ignore_comments

        if self._ignore_comments:
            self.token_indexes = [idx for idx in range(len(srcfile.tokens))
                                  if srcfile.tokens[idx].type not in {tokenize.COMMENT}]
        else:
            self.token_indexes = list(range(len(srcfile.tokens)))  # [0, 1, ..., len(srcfile.tokens)-1]

    def match_on(self, matcher_list: list[Matcher]) -> None:
        self._matcher_list_list.append(matcher_list)

    def _check_nolint_suppression(self, token: TokenInfo) -> bool:
        if token.type not in {tokenize.COMMENT} or "noqa" not in token.string:
            return False

        match = re.fullmatch(r".*noqa\(([^)]+)\).*", token.string)
        if not match:
            return False
        nolint_str = match.group(1)
        suppressed_checks = [s.strip() for s in nolint_str.split(',')]
        return self._rule_name in suppressed_checks

    def __iter__(self) -> Iterator[tuple[TokenInfo, TokenInfo]]:
        for matcher_list in self._matcher_list_list:
            index = 0  # next index of token to try matching

            token_seq = TokenSequence(self._srcfile.tokens, self.token_indexes, self._srcfile.sentinel_token)
            while True:
                assert len(matcher_list) >= 1
                if index + len(matcher_list) >= len(self.token_indexes):
                    break

                cursor = index
                for matcher in matcher_list:
                    token_seq.cursor = cursor
                    matcher_result: int = matcher(token_seq)
                    if matcher_result < 0:
                        index += 1
                        break
                    else:  # matcher_result >= 0
                        cursor += matcher_result
                else:
                    assert cursor > index
                    from_token = self._srcfile.tokens[self.token_indexes[index]]
                    to_token = self._srcfile.tokens[self.token_indexes[cursor - 1]]
                    index += 1

                    for token in itertools.chain(*(self._srcfile.tokens_by_line[line_num]
                                                   for line_num
                                                   in range(from_token.start[0], to_token.end[0] + 1))):
                        if self._check_nolint_suppression(token):
                            # It's suppressed by comment...
                            break
                    else:
                        yield from_token, to_token

    def print_message_with_highlight(self, from_token: TokenInfo, to_token: TokenInfo, prefix: str, message: str):
        from_line = from_token.start[0]
        from_col = from_token.start[1] + 1
        to_line = to_token.end[0]
        to_col = to_token.end[1] + 1
        assert (from_line, from_col) < (to_line, to_col)

        file_and_pos = f"{self._srcfile.file}:{from_line}:{from_col}"
        print(f"{prefix}Check \"{self._rule_name}\" at {file_and_pos}")
        for message_per_line in message.splitlines(keepends=False):
            print(f"{prefix}{message_per_line}")

        for line in range(from_line, to_line + 1):
            # Expand TAB to a single space, so '^^^' markers work well with TAB character (though we shouldn't use TABs)
            str_line = self._srcfile.lines[line - 1].expandtabs(1)

            prefix_line_num_str = f"line {line} |".rjust(11)
            prefix_line_num_space = "|".rjust(len(prefix_line_num_str))
            print(f"{prefix}{prefix_line_num_str} {str_line}")

            if line == from_line and line == to_line:  # in a single line
                print(f"{prefix}{prefix_line_num_space} {' ' * (from_col - 1)}{'^' * (to_col - from_col)}")
            elif line == from_line:  # across multiple lines, and this is the first line
                print(f"{prefix}{prefix_line_num_space} {' ' * (from_col - 1)}{'^' * (len(str_line) - from_col + 1)}")
            elif line == to_line:  # across multiple lines, and this is the last line
                print(f"{prefix}{prefix_line_num_space} {'^' * to_col}")
            else:  # across multiple lines, and this is a line in the middle
                print(f"{prefix}{prefix_line_num_space} {'^' * len(str_line)}")
        print()

    def check(self, prefix, message):
        success = True
        for from_token, to_token in self:
            self.print_message_with_highlight(from_token, to_token, prefix, message)
            success = False
        return success


class Matcher(ABC):
    def __call__(self, token_seq: TokenSequence) -> int:
        """
        Returns the number of tokens matched, or -1 if not matched.
        """
        raise NotImplementedError()


class ExceptMatcher(Matcher):
    def __init__(self, base_matcher: Matcher, except_matcher: Matcher) -> None:
        self._base_matcher = base_matcher
        self._except_matcher = except_matcher

    def __call__(self, token_seq: TokenSequence) -> int:
        base_matcher_result = self._base_matcher(token_seq)
        if base_matcher_result < 0:
            return base_matcher_result

        except_matcher_result = self._except_matcher(token_seq)
        if except_matcher_result >= 0:
            return -1

        return base_matcher_result


class TokenTextMatcher(Matcher):
    def __init__(self, tokens_text: list[Union[str, re.Pattern]]) -> None:
        assert len(tokens_text) > 0
        self._tokens_text = tokens_text

    def __call__(self, token_seq: TokenSequence) -> int:
        for i, token_text in enumerate(self._tokens_text):
            if isinstance(token_text, str):
                if token_seq[i].string != token_text:
                    return -1
            elif isinstance(token_text, re.Pattern):
                if not token_text.fullmatch(token_seq[i].string):
                    return -1
            else:
                raise TypeError(f"Invalid token_text type: {type(token_text)}")
        return len(self._tokens_text)


class TokenTypeMatcher(Matcher):
    def __init__(self, tokens_type: list[TokenType]) -> None:
        assert len(tokens_type) > 0
        self._tokens_type = tokens_type

    def __call__(self, token_seq: TokenSequence) -> int:
        for i, token_type in enumerate(self._tokens_type):
            if token_seq[i].type != token_type:
                return -1
        return len(self._tokens_type)


class SingleTokenMatcher(Matcher):
    def __init__(self, predicate):
        self._predicate = predicate

    def __call__(self, token_seq: TokenSequence) -> int:
        if self._predicate(token_seq[0]):
            return 1
        else:
            return -1


class PythonExprMatcher(Matcher):
    def __call__(self, token_seq: TokenSequence) -> int:
        """
        Match a Python expression as a function (actual) argument.
        """
        # Check the previous token to see if this is the start of a function actual argument
        if token_seq[-1].string not in (',', '('):
            return -1

        # Use a stack to keep track of nested function calls
        nested_parentheses = 0
        i = 0
        while True:
            if token_seq[i].type == tokenize.ENCODING:
                return -1

            if nested_parentheses == 0:
                # If we're not in a nested function call, and we see a comma or a closing parenthesis,
                # we've found the end of the actual argument
                if token_seq[i].type == tokenize.OP and token_seq[i].string in (",", ")"):
                    return i

            if token_seq[i].type == tokenize.OP and token_seq[i].string == '(':
                nested_parentheses += 1
            elif token_seq[i].type == tokenize.OP and token_seq[i].string == ')':
                nested_parentheses -= 1
            i += 1


def do_check_suppress_warning(srcfile: SourceFile) -> bool:
    """
    Check that we do not use `contextlib.suppress(XxxWarning)`,
    use `warnings.catch_warnings(action="ignore", category=XxxWarning)` instead.
    """
    checker = Checker("ml-ignore-warning", srcfile, ignore_comments=True)
    checker.match_on([
        TokenTextMatcher(["suppress", "(", re.compile(".*Warning")]),
    ])

    return checker.check(
        "ERROR: ", "Please do not use `contextlib.suppress(XxxWarning)`; use `warnings.catch_warnings(...)` instead.")


def do_check_typing_cast(srcfile: SourceFile) -> bool:
    """
    Check that we do not use `typing.cast()`,
    use `common.type_hints.safe_cast()` instead.
    """
    checker = Checker("ml-typing-cast", srcfile, ignore_comments=False)
    checker.match_on([
        TokenTextMatcher(["cast", "("]),
        TokenTypeMatcher([tokenize.NAME]),
    ])

    return checker.check(
        "ERROR: ", "Please do not use `typing.cast(T, value)`, use `safe_cast(T, value)` instead.")


def do_check_test_directory_name(srcfile: SourceFile) -> bool:
    """
    Check that we always use "test" as test directory name.
    Do not use "tests" or "unittest" or anything else.
    """
    srcfile_path: Path = Path(srcfile.file)
    parts_lower: list[str] = [part.lower() for part in srcfile_path.parts]
    disallowed_names: list[str] = ["tests", "unittest", "unit_test", "unittests", "unit_tests"]
    for disallowed_name in disallowed_names:
        if disallowed_name in parts_lower:
            print(f"ERROR: {srcfile_path}: Please use 'test' as the test directory name, not {disallowed_name!r}.")
            return False
    return True


def main():
    repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(repo_dir)

    files: list[str] = []
    for pattern in {"memorylake/**/*.py"}:
        files += glob.glob(pattern, recursive=True)

    success: bool = True
    for file in files:
        # print(f"Checking {file}")
        srcfile = SourceFile(file)

        success = do_check_suppress_warning(srcfile) and success
        success = do_check_typing_cast(srcfile) and success
        success = do_check_test_directory_name(srcfile) and success

    return 0 if success else 1


if __name__ == '__main__':
    exit(main())
