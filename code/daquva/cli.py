"""Command line interface for DaQuVa."""

from __future__ import annotations

import argparse
from pathlib import Path

from daquva.lexer import Lexer
from daquva.parser import Parser
from daquva.runtime import Runtime


def run_file(path: Path, *, print_tokens: bool = False, print_ast: bool = False) -> None:
    source = path.read_text(encoding="utf-8")
    tokens = Lexer(source).tokenize()
    if print_tokens:
        for token in tokens:
            print(token)
    program = Parser(tokens).parse()
    if print_ast:
        print(program)
    Runtime(base_path=path.parent).run(program)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a DaQuVa .dqv program")
    parser.add_argument("source", type=Path, help="Path to a .dqv file")
    parser.add_argument("--tokens", action="store_true", help="Print lexer tokens before execution")
    parser.add_argument("--ast", action="store_true", help="Print parsed AST before execution")
    args = parser.parse_args()

    run_file(args.source.resolve(), print_tokens=args.tokens, print_ast=args.ast)


if __name__ == "__main__":
    main()
