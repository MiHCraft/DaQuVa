"""Interactive REPL for DaQuVa."""

from __future__ import annotations

import sys
from pathlib import Path

from daquva.lexer import Lexer, TokenType
from daquva.parser import Parser
from daquva.runtime import Runtime
from daquva.ast_nodes import ConnectionDecl
from daquva.table import Table
from daquva.execution_engine import ExecutionEngine
from daquva.utils.pretty_print import pretty_print

_BANNER = """\
+------------------------------------------+
|  DaQuVa  --  Data Quality Validator REPL |
|  :help   :tables   :vars   :quit         |
+------------------------------------------+"""

_HELP = """\
Commands:
  Any DaQuVa statement ending with ;   — execute it
  :tables                              — list active connections
  :vars                                — list in-memory table variables
  :help                                — show this message
  :quit  /  Ctrl-D                     — exit

Tips:
  • Declare connections first:  csv people "data.csv";
  • Assign results:             adults = filter people where age >= 18;
  • Print a table:              adults -> console;
  • Statements can span lines — keep typing until you add a ;
"""


def run_repl(base_path: Path | None = None) -> None:
    print(_BANNER)
    runtime = Runtime(base_path or Path.cwd())
    buffer: list[str] = []

    while True:
        prompt = "daquva> " if not buffer else "     .. "
        try:
            line = input(prompt)
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break

        stripped = line.strip()

        # Meta-commands
        if not buffer and stripped.startswith(":"):
            _handle_meta(stripped, runtime)
            continue

        buffer.append(line)
        combined = " ".join(buffer)

        # Only attempt parse when the buffer contains at least one semicolon
        # (or a closing brace for function definitions)
        if ";" not in combined and "}" not in combined:
            continue

        # Try to execute; if we get a parse error that looks like incomplete
        # input, keep buffering.
        try:
            _execute_snippet(combined, runtime)
            buffer = []
        except SyntaxError as exc:
            msg = str(exc)
            # Incomplete input: the parser hit EOF — keep buffering
            if "EOF" in msg or "end of input" in msg.lower():
                continue
            buffer = []
            print(f"  Syntax error: {exc}")
        except Exception as exc:
            buffer = []
            print(f"  Error: {exc}")


def _execute_snippet(source: str, runtime: Runtime) -> None:
    tokens = Lexer(source).tokenize()
    parser = Parser(tokens)

    # Connections at the front of the buffer get registered separately
    connections: list[ConnectionDecl] = []
    while parser._peek().type in {TokenType.SQLITE, TokenType.CSV}:
        connections.append(parser._connection())

    for conn in connections:
        runtime._register_connection(conn)
        print(f"  Connected: {conn.name!r} ({conn.kind.upper()}) -> {conn.path}")

    if parser._peek().type == TokenType.EOF:
        return

    # Parse remaining statements
    statements = []
    while parser._peek().type != TokenType.EOF:
        if parser._match(TokenType.SEMICOLON):
            continue
        statements.append(parser._statement())
        parser._expect(TokenType.SEMICOLON)

    for statement in statements:
        from daquva.ast_nodes import Assignment, OutputStatement, SaveStatement
        if isinstance(statement, Assignment):
            value = runtime._evaluate(statement.expression)
            runtime.memory[statement.target] = value
            if isinstance(value, Table):
                mat = runtime.engine.materialize(value)
                rows_word = "row" if len(mat.rows) == 1 else "rows"
                print(f"  >> {statement.target!r}: {len(mat.rows)} {rows_word}, "
                      f"{len(mat.columns)} columns: {', '.join(mat.columns)}")
            else:
                print(f"  >> {statement.target!r} = {value!r}")
        elif isinstance(statement, OutputStatement):
            runtime._execute_output(statement)
        elif isinstance(statement, SaveStatement):
            runtime._execute_save(statement)
        else:
            result = runtime._evaluate(statement)
            if isinstance(result, Table):
                mat = runtime.engine.materialize(result)
                print(pretty_print(mat.columns, mat.rows))


def _handle_meta(command: str, runtime: Runtime) -> None:
    cmd = command.lower()
    if cmd in (":quit", ":exit", ":q"):
        print("Bye.")
        sys.exit(0)
    elif cmd == ":help":
        print(_HELP)
    elif cmd == ":tables":
        if not runtime.connections:
            print("  No connections registered.")
        for name, conn in runtime.connections.items():
            kind = conn.kind.upper()
            try:
                schema = conn.get_schema(name)
                print(f"  {name!r} ({kind}) — tables/columns available")
            except Exception:
                print(f"  {name!r} ({kind})")
    elif cmd == ":vars":
        if not runtime.memory:
            print("  No variables defined.")
        for name, value in runtime.memory.items():
            if isinstance(value, Table):
                print(f"  {name!r}: table ({len(value.columns)} columns: {', '.join(value.columns)})")
            else:
                print(f"  {name!r}: {value!r}")
    else:
        print(f"  Unknown command {command!r}. Type :help for help.")
