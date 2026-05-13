"""Tokenization for the DaQuVa DSL."""

from __future__ import annotations

import ast as py_ast
import re
from dataclasses import dataclass
from enum import Enum, auto


class TokenType(Enum):
    ARROW = auto()
    EQ = auto()
    NE = auto()
    LE = auto()
    GE = auto()
    LT = auto()
    GT = auto()
    ASSIGN = auto()
    SEMICOLON = auto()
    COMMA = auto()
    COLON = auto()
    DOT = auto()
    LPAREN = auto()
    RPAREN = auto()
    LBRACKET = auto()
    RBRACKET = auto()
    STRING = auto()
    NUMBER = auto()
    IDENTIFIER = auto()
    SQLITE = auto()
    CSV = auto()
    SCAN = auto()
    USING_TOOL = auto()
    USING = auto()
    TOOL = auto()
    FILTER = auto()
    WHERE = auto()
    STARTS_WITH = auto()
    OUTPUT = auto()
    CONSOLE = auto()
    DATABASE = auto()
    FILE = auto()
    SAVE = auto()
    INTO = auto()
    ALLOW_DANGER = auto()
    FIND_DUPLICATES = auto()
    MERGE = auto()
    ADD_ROWS = auto()
    ADD_COLUMNS = auto()
    EDIT_ROWS = auto()
    EDIT_COLUMNS = auto()
    DELETE_COLUMNS = auto()
    DELETE_ROWS = auto()
    RENAME = auto()
    TO = auto()
    SET = auto()
    TRUE = auto()
    FALSE = auto()
    NUMBER_TYPE = auto()
    STRING_TYPE = auto()
    BOOL_TYPE = auto()
    TABLE_TYPE = auto()
    EOF = auto()


KEYWORDS = {
    "sqlite": TokenType.SQLITE,
    "csv": TokenType.CSV,
    "scan": TokenType.SCAN,
    "using_tool": TokenType.USING_TOOL,
    "using": TokenType.USING,
    "tool": TokenType.TOOL,
    "filter": TokenType.FILTER,
    "where": TokenType.WHERE,
    "starts_with": TokenType.STARTS_WITH,
    "output": TokenType.OUTPUT,
    "console": TokenType.CONSOLE,
    "database": TokenType.DATABASE,
    "file": TokenType.FILE,
    "save": TokenType.SAVE,
    "into": TokenType.INTO,
    "allowDanger": TokenType.ALLOW_DANGER,
    "find_duplicates": TokenType.FIND_DUPLICATES,
    "merge": TokenType.MERGE,
    "add_rows": TokenType.ADD_ROWS,
    "add_columns": TokenType.ADD_COLUMNS,
    "edit_rows": TokenType.EDIT_ROWS,
    "edit_columns": TokenType.EDIT_COLUMNS,
    "delete_columns": TokenType.DELETE_COLUMNS,
    "delete_rows": TokenType.DELETE_ROWS,
    "rename": TokenType.RENAME,
    "to": TokenType.TO,
    "set": TokenType.SET,
    "true": TokenType.TRUE,
    "false": TokenType.FALSE,
    "number": TokenType.NUMBER_TYPE,
    "string": TokenType.STRING_TYPE,
    "bool": TokenType.BOOL_TYPE,
    "table": TokenType.TABLE_TYPE,
}


TOKEN_SPEC = [
    ("COMMENT", r"//[^\n]*|#[^\n]*"),
    ("SKIP", r"[ \t\r\n]+"),
    ("ARROW", r"->"),
    ("EQ", r"=="),
    ("NE", r"!="),
    ("LE", r"<="),
    ("GE", r">="),
    ("LT", r"<"),
    ("GT", r">"),
    ("ASSIGN", r"="),
    ("SEMICOLON", r";"),
    ("COMMA", r","),
    ("COLON", r":"),
    ("DOT", r"\."),
    ("LPAREN", r"\("),
    ("RPAREN", r"\)"),
    ("LBRACKET", r"\["),
    ("RBRACKET", r"\]"),
    ("STRING", r'"(?:[^"\\]|\\.)*"'),
    ("NUMBER", r"\d+(?:\.\d+)?"),
    ("IDENTIFIER", r"[A-Za-z_][A-Za-z0-9_]*"),
]

COMPILED_TOKEN_SPEC = [(name, re.compile(pattern)) for name, pattern in TOKEN_SPEC]


@dataclass(frozen=True)
class Token:
    type: TokenType
    value: object = None
    line: int = 1
    column: int = 1

    def __repr__(self) -> str:
        return f"{self.type.name}({self.value!r}) at {self.line}:{self.column}"


class Lexer:
    def __init__(self, code: str):
        self.code = code
        self.pos = 0
        self.line = 1
        self.column = 1

    def tokenize(self) -> list[Token]:
        tokens: list[Token] = []

        while self.pos < len(self.code):
            for name, regex in COMPILED_TOKEN_SPEC:
                match = regex.match(self.code, self.pos)
                if not match:
                    continue

                text = match.group(0)
                line = self.line
                column = self.column
                self._advance(text)

                if name in {"SKIP", "COMMENT"}:
                    break

                if name == "IDENTIFIER":
                    token_type = KEYWORDS.get(text, TokenType.IDENTIFIER)
                    tokens.append(Token(token_type, text, line, column))
                    break

                if name == "STRING":
                    tokens.append(Token(TokenType.STRING, py_ast.literal_eval(text), line, column))
                    break

                if name == "NUMBER":
                    value = float(text) if "." in text else int(text)
                    tokens.append(Token(TokenType.NUMBER, value, line, column))
                    break

                tokens.append(Token(TokenType[name], text, line, column))
                break
            else:
                char = self.code[self.pos]
                raise SyntaxError(
                    f"Unexpected character {char!r} at line {self.line}, column {self.column}"
                )

        tokens.append(Token(TokenType.EOF, None, self.line, self.column))
        return tokens

    def _advance(self, text: str) -> None:
        for char in text:
            if char == "\n":
                self.line += 1
                self.column = 1
            else:
                self.column += 1
        self.pos += len(text)
