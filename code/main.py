"""
DaQuVa DSL — Complete Lexer + Parser  →  AST
=============================================
Implements the BNF grammar from Chapter 2 of the DaQuVa specification.

РАСХОЖДЕНИЯ между PDF-спецификацией и загруженным Python-прототипом
────────────────────────────────────────────────────────────────────
#  | Что в PDF (спецификация)            | Что в прототипе           | Решение
---|--------------------------------------|---------------------------|---------------------------
1  | keyword `function`                  | keyword `def`             | используем `function`
2  | тело функции открывается через `:`  | нет `:`, тело идёт сразу  | добавляем токен COLON
3  | тело функции — <statementblock>;    | закрывается через `end`   | используем `end` *
   | <statementblock> рекурсивен, нет    |                           | (единственно возможно
   | явного терминатора в грамматике     |                           | в whitespace-free языке)
4  | `return` — ключевое слово (табл.    | отсутствует полностью     | добавляем ReturnStatement
   | 2.2.1), но нет BNF-продукции        |                           |
5  | <tablename> ::= <string>            | consume('ID')             | принимаем и STRING, и ID *
   | но пример: scan tablename."email"   |                           | (имя таблицы может быть
   | где tablename — параметр функции    |                           | переменной)
6  | <expression> ::= <id> <op> <num>   | полные binary expressions | RHS расширяем до <value> *
   | но пример: dirtylevel > threshold   |                           | (threshold — переменная)
7  | `columns` keyword (findLocalDupl.)  | keyword `on`              | используем `columns`
8  | Here(n) offset — опциональный       | обязателен                | делаем опциональным
9  | `from` / `addColumns` — опциональны | не проверено              | оба опциональны
10 | `allowDanger` — опционален в BNF,   | обязателен жёстко         | обязателен **
   | но §2.3.3: "compile-time error      |                           |
   | if absent"                          |                           |
11 | `#` single-line comments (§2.2.2)   | не обрабатываются         | добавляем в lexer
12 | Нет AST-узла ReturnStatement        | —                         | добавляем

* — clarification, не противоречие: спецификация неполна или пример противоречит BNF.
** — следуем семантике (§2.3.3), а не BNF.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Union


# ═══════════════════════════════════════════════════════════════════════════
#  1.  AST NODES
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class ASTNode:
    """Abstract base for all AST nodes."""


# ── Top-level constructs ───────────────────────────────────────────────────

@dataclass
class Program(ASTNode):
    """Root node: ordered list of top-level statements."""
    statements: List[ASTNode]


@dataclass
class DatabaseInit(ASTNode):
    """my db "<connection_string>" ;"""
    connection: str


@dataclass
class FunctionDef(ASTNode):
    """function <name>(<params>) : <body> end"""
    name:   str
    params: List[str]
    body:   List[ASTNode]


@dataclass
class Assignment(ASTNode):
    """<name> = <rhs> ;"""
    name:  str
    value: ASTNode


@dataclass
class ReturnStatement(ASTNode):
    """return <value> ;   — only valid inside a function body."""
    value: ASTNode


# ── Commands ───────────────────────────────────────────────────────────────

@dataclass
class Scan(ASTNode):
    """scan <table_ref>."<column>" using tool "<tool>" ;

    table  — Variable (passed as a parameter) or Literal str (quoted name).
    column — the column-name string (without quotes in the AST).
    tool   — the tool-name string.
    """
    table:  ASTNode   # Variable | Literal(str)
    column: str
    tool:   str


@dataclass
class Filter(ASTNode):
    """filter <source> where <condition> ;"""
    source:    str        # identifier of the result-set to filter
    condition: ASTNode   # BinaryOp tree built from AND / OR / comparison ops


@dataclass
class FindDuplicates(ASTNode):
    """findLocalDuplicates <source> columns ["<c1>", ...] [using tool "<t>"] ;"""
    source:  str
    columns: List[str]        # column names — always string literals in the source
    tool:    Optional[str]    # None when `using tool` clause is absent


@dataclass
class Merge(ASTNode):
    """merge <source> -> Here[(<threshold>)] allowDanger ;"""
    source:    str
    threshold: Optional[int]  # None → runtime uses default (0)


@dataclass
class Output(ASTNode):
    """output <source> -> console | file "<path>" | Here[(<threshold>)] ;"""
    source:    str
    target:    str             # 'console' | 'file' | 'database'
    path:      Optional[str] = None
    threshold: Optional[int] = None


@dataclass
class NewTable(ASTNode):
    """newTable "<name>" [from <source>] [addColumns [<items>]] ;"""
    name:    str
    source:  Optional[str]   # identifier of source result-set; None if absent
    columns: List[ASTNode]   # Literal(str) | Variable | FunctionCall


# ── Expressions ────────────────────────────────────────────────────────────

@dataclass
class BinaryOp(ASTNode):
    """<left> <op> <right>
    op is one of: AND OR  >  <  >=  <=  ==  !=
    """
    left:  ASTNode
    op:    str
    right: ASTNode


@dataclass
class FunctionCall(ASTNode):
    """<name>(<args>)"""
    name: str
    args: List[ASTNode]


@dataclass
class Variable(ASTNode):
    """Reference to a named variable or function parameter."""
    name: str


@dataclass
class Literal(ASTNode):
    """Integer or string literal value."""
    value: Union[int, str]


# ═══════════════════════════════════════════════════════════════════════════
#  2.  LEXER
# ═══════════════════════════════════════════════════════════════════════════

#: Every reserved word.  A WORD token matching one of these becomes KW.
KEYWORDS: frozenset = frozenset({
    # database
    'my', 'db',
    # function & control  (§2.2.2 Table 2.2.1)
    'function', 'return', 'end',
    # commands
    'scan', 'filter', 'merge', 'output', 'newTable', 'findLocalDuplicates',
    # conditions / logic
    'where', 'AND', 'OR',
    # column-list keyword (findLocalDuplicates)
    'columns',
    # tool integration
    'using', 'tool',
    # output targets and table modifiers
    'console', 'file', 'from', 'addColumns',
    # safety
    'Here', 'allowDanger',
})


class Token:
    """Immutable token produced by the lexer."""
    __slots__ = ('kind', 'value', 'pos')

    def __init__(self, kind: str, value, pos: int) -> None:
        self.kind  = kind
        self.value = value
        self.pos   = pos

    def __repr__(self) -> str:
        return f'Token({self.kind}, {self.value!r}, pos={self.pos})'


class LexerError(Exception):
    pass


class Lexer:
    """
    Converts a DaQuVa source string into a flat sequence of Tokens.

    Token kinds
    ───────────
    KW        — reserved keyword  (value is the keyword string)
    ID        — user identifier   (value is the name string)
    STRING    — double-quoted literal, quotes stripped from value
    NUMBER    — non-negative integer literal, value is int
    ARROW     — '->'
    COMP_OP   — one of  !=  ==  >=  <=  >  <
    ASSIGN    — '='
    COLON     — ':'
    SEMICOLON — ';'
    LPAREN    — '('
    RPAREN    — ')'
    LBRACKET  — '['
    RBRACKET  — ']'
    DOT       — '.'
    COMMA     — ','
    EOF       — synthetic sentinel, never stored; returned by peek() past end
    """

    _RULES: list = [
        ('COMMENT',   r'#[^\n]*'),          # single-line comment — discarded
        ('STRING',    r'"[^"]*"'),
        ('NUMBER',    r'\d+'),
        ('ARROW',     r'->'),
        # Multi-char operators must come before single-char ones
        ('COMP_OP',   r'!=|==|>=|<=|>|<'),
        ('COLON',     r':'),
        ('ASSIGN',    r'='),
        ('SEMICOLON', r';'),
        ('LPAREN',    r'\('),
        ('RPAREN',    r'\)'),
        ('LBRACKET',  r'\['),
        ('RBRACKET',  r'\]'),
        ('DOT',       r'\.'),
        ('COMMA',     r','),
        ('WORD',      r'[A-Za-z_]\w*'),     # identifier or keyword
        ('SKIP',      r'[ \t\r\n]+'),       # whitespace — discarded
        ('MISMATCH',  r'.'),                # anything else → error
    ]

    _MASTER = re.compile(
        '|'.join(f'(?P<{name}>{pattern})' for name, pattern in _RULES)
    )

    def __init__(self, source: str) -> None:
        self._tokens: list = []
        self._pos: int = 0
        self._tokenise(source)

    def _tokenise(self, source: str) -> None:
        for mo in self._MASTER.finditer(source):
            kind = mo.lastgroup
            raw  = mo.group()
            pos  = mo.start()

            if kind in ('SKIP', 'COMMENT'):
                continue
            if kind == 'MISMATCH':
                raise LexerError(
                    f"Illegal character {raw!r} at source position {pos}"
                )
            if kind == 'STRING':
                self._tokens.append(Token('STRING', raw[1:-1], pos))
            elif kind == 'NUMBER':
                self._tokens.append(Token('NUMBER', int(raw), pos))
            elif kind == 'WORD':
                tok_kind = 'KW' if raw in KEYWORDS else 'ID'
                self._tokens.append(Token(tok_kind, raw, pos))
            else:
                self._tokens.append(Token(kind, raw, pos))

    # ── navigation ──────────────────────────────────────────────────────────

    _EOF = Token('EOF', None, -1)

    def peek(self, offset: int = 0) -> Token:
        idx = self._pos + offset
        return self._tokens[idx] if idx < len(self._tokens) else self._EOF

    def consume(self,
                expected_kind: Optional[str] = None,
                expected_val=None) -> Token:
        tok = self.peek()
        if expected_kind is not None and tok.kind != expected_kind:
            detail = (f" with value {expected_val!r}"
                      if expected_val is not None else "")
            raise SyntaxError(
                f"Expected token {expected_kind!r}{detail}, "
                f"got {tok.kind!r} ({tok.value!r}) at position {tok.pos}"
            )
        if expected_val is not None and tok.value != expected_val:
            raise SyntaxError(
                f"Expected value {expected_val!r}, "
                f"got {tok.value!r} at position {tok.pos}"
            )
        self._pos += 1
        return tok


# ═══════════════════════════════════════════════════════════════════════════
#  3.  PARSER
# ═══════════════════════════════════════════════════════════════════════════

class ParseError(SyntaxError):
    pass


class Parser:
    """
    Recursive-descent parser.

    Public API:   parser.parse()  →  Program
    """

    def __init__(self, lexer: Lexer) -> None:
        self._lx = lexer

    # ── shorthand helpers ───────────────────────────────────────────────────

    def _peek(self, offset: int = 0) -> Token:
        return self._lx.peek(offset)

    def _consume(self, kind: Optional[str] = None, val=None) -> Token:
        return self._lx.consume(kind, val)

    def _at_end(self) -> bool:
        return self._peek().kind == 'EOF'

    def _is(self, kind: str, val=None, offset: int = 0) -> bool:
        tok = self._peek(offset)
        return tok.kind == kind and (val is None or tok.value == val)

    # ── program ─────────────────────────────────────────────────────────────

    def parse(self) -> Program:
        stmts: list = []
        while not self._at_end():
            stmts.append(self._parse_statement())
        return Program(stmts)

    # ── statement dispatcher ────────────────────────────────────────────────

    def _parse_statement(self) -> ASTNode:
        tok = self._peek()

        if tok.kind == 'KW':
            if tok.value == 'my':
                return self._parse_db_init()
            if tok.value == 'function':
                return self._parse_function_def()
            if tok.value == 'return':
                return self._parse_return()
            # Any other keyword starts a command statement
            node = self._parse_command(context='statement')
            self._consume('SEMICOLON')
            return node

        if tok.kind == 'ID':
            # Two possibilities:
            #   <id> =  ...  →  variable assignment
            #   <id> (  ...  →  bare function call
            if self._is('ASSIGN', offset=1):
                return self._parse_assignment()
            if self._is('LPAREN', offset=1):
                node = self._parse_function_call()
                self._consume('SEMICOLON')
                return node
            raise ParseError(
                f"Unexpected token after identifier {tok.value!r}: "
                f"{self._peek(1)} at pos {self._peek(1).pos}"
            )

        raise ParseError(
            f"Unexpected token {tok.kind!r} ({tok.value!r}) at pos {tok.pos}"
        )

    # ── my db ───────────────────────────────────────────────────────────────

    def _parse_db_init(self) -> DatabaseInit:
        self._consume('KW', 'my')
        self._consume('KW', 'db')
        conn = self._consume('STRING').value
        self._consume('SEMICOLON')
        return DatabaseInit(conn)

    # ── function definition ─────────────────────────────────────────────────

    def _parse_function_def(self) -> FunctionDef:
        self._consume('KW', 'function')
        name = self._consume('ID').value
        self._consume('LPAREN')
        params = self._parse_param_list()
        self._consume('RPAREN')
        self._consume('COLON')          # ':' separates header from body

        body: list = []
        while not self._is('KW', 'end'):
            if self._at_end():
                raise ParseError(
                    f"Unexpected EOF inside function '{name}'; missing 'end'"
                )
            body.append(self._parse_statement())
        self._consume('KW', 'end')
        return FunctionDef(name, params, body)

    def _parse_param_list(self) -> list:
        params: list = []
        while not self._is('RPAREN'):
            params.append(self._consume('ID').value)
            if self._is('COMMA'):
                self._consume('COMMA')
        return params

    # ── return ──────────────────────────────────────────────────────────────

    def _parse_return(self) -> ReturnStatement:
        self._consume('KW', 'return')
        val = self._parse_value_node()
        self._consume('SEMICOLON')
        return ReturnStatement(val)

    # ── assignment ──────────────────────────────────────────────────────────

    def _parse_assignment(self) -> Assignment:
        name = self._consume('ID').value
        self._consume('ASSIGN')
        rhs = self._parse_command(context='rhs')
        self._consume('SEMICOLON')
        return Assignment(name, rhs)

    # ── command dispatcher ──────────────────────────────────────────────────

    def _parse_command(self, context: str = 'statement') -> ASTNode:
        """
        Parse one command.  Does NOT consume the trailing semicolon —
        the caller is responsible.

        context = 'rhs'       — called from assignment, RHS may be a
                                function call starting with ID.
        context = 'statement' — called from statement dispatcher, token
                                is guaranteed to be a KW.
        """
        tok = self._peek()

        # Function call on the RHS of an assignment
        if tok.kind == 'ID' and context == 'rhs':
            return self._parse_function_call()

        if tok.kind != 'KW':
            raise ParseError(
                f"Expected a command keyword, "
                f"got {tok.kind!r} ({tok.value!r}) at pos {tok.pos}"
            )

        dispatch = {
            'scan':                self._parse_scan,
            'filter':              self._parse_filter,
            'findLocalDuplicates': self._parse_find_duplicates,
            'merge':               self._parse_merge,
            'output':              self._parse_output,
            'newTable':            self._parse_new_table,
        }
        parser_fn = dispatch.get(tok.value)
        if parser_fn is None:
            raise ParseError(
                f"Unknown command keyword {tok.value!r} at pos {tok.pos}"
            )
        return parser_fn()

    # ── scan ────────────────────────────────────────────────────────────────

    def _parse_scan(self) -> Scan:
        """scan <table_ref>."<column>" using tool "<tool>" """
        self._consume('KW', 'scan')
        table  = self._parse_table_ref()
        self._consume('DOT')
        column = self._consume('STRING').value
        self._consume('KW', 'using')
        self._consume('KW', 'tool')
        tool   = self._consume('STRING').value
        return Scan(table, column, tool)

    def _parse_table_ref(self) -> ASTNode:
        """
        <tablename> ::= <string> | <identifier>
        Accepts a quoted string (literal table name) OR a bare identifier
        (variable holding the table name, e.g. a function parameter).
        """
        tok = self._peek()
        if tok.kind == 'STRING':
            return Literal(self._consume('STRING').value)
        if tok.kind == 'ID':
            return Variable(self._consume('ID').value)
        raise ParseError(
            f"Expected table name (ID or STRING), "
            f"got {tok.kind!r} ({tok.value!r}) at pos {tok.pos}"
        )

    # ── filter ──────────────────────────────────────────────────────────────

    def _parse_filter(self) -> Filter:
        """filter <source> where <condition>"""
        self._consume('KW', 'filter')
        source = self._consume('ID').value
        self._consume('KW', 'where')
        condition = self._parse_condition()
        return Filter(source, condition)

    def _parse_condition(self) -> ASTNode:
        """<condition> ::= <comparison> (('AND' | 'OR') <comparison>)*"""
        node = self._parse_comparison()
        while self._is('KW', 'AND') or self._is('KW', 'OR'):
            op    = self._consume('KW').value          # 'AND' or 'OR'
            right = self._parse_comparison()
            node  = BinaryOp(node, op, right)
        return node

    def _parse_comparison(self) -> ASTNode:
        """<expression> ::= <value> <comp_op> <value>"""
        left = self._parse_value_node()
        if not self._is('COMP_OP'):
            raise ParseError(
                f"Expected comparison operator after value, "
                f"got {self._peek().kind!r} ({self._peek().value!r}) "
                f"at pos {self._peek().pos}"
            )
        op    = self._consume('COMP_OP').value
        right = self._parse_value_node()
        return BinaryOp(left, op, right)

    # ── findLocalDuplicates ─────────────────────────────────────────────────

    def _parse_find_duplicates(self) -> FindDuplicates:
        """findLocalDuplicates <source> columns ["<c1>", ...] [using tool "<t>"]"""
        self._consume('KW', 'findLocalDuplicates')
        source = self._consume('ID').value
        self._consume('KW', 'columns')
        self._consume('LBRACKET')
        cols = self._parse_string_list()
        self._consume('RBRACKET')
        tool: Optional[str] = None
        if self._is('KW', 'using'):
            self._consume('KW', 'using')
            self._consume('KW', 'tool')
            tool = self._consume('STRING').value
        return FindDuplicates(source, cols, tool)

    def _parse_string_list(self) -> list:
        """Comma-separated list of quoted string literals (column names)."""
        items: list = []
        while not self._is('RBRACKET'):
            items.append(self._consume('STRING').value)
            if self._is('COMMA'):
                self._consume('COMMA')
        return items

    # ── merge ───────────────────────────────────────────────────────────────

    def _parse_merge(self) -> Merge:
        """merge <source> -> Here[(<threshold>)] allowDanger"""
        self._consume('KW', 'merge')
        source = self._consume('ID').value
        self._consume('ARROW')
        self._consume('KW', 'Here')
        threshold = self._parse_opt_threshold()
        # allowDanger is REQUIRED (§2.3.3: "compile-time error if absent")
        if not self._is('KW', 'allowDanger'):
            raise ParseError(
                f"'allowDanger' is required after 'merge -> Here(...)'; "
                f"got {self._peek().kind!r} ({self._peek().value!r}) "
                f"at pos {self._peek().pos}"
            )
        self._consume('KW', 'allowDanger')
        return Merge(source, threshold)

    def _parse_opt_threshold(self) -> Optional[int]:
        """Optional '(' <number> ')' offset / confidence argument."""
        if self._is('LPAREN'):
            self._consume('LPAREN')
            value = self._consume('NUMBER').value
            self._consume('RPAREN')
            return value
        return None

    # ── output ──────────────────────────────────────────────────────────────

    def _parse_output(self) -> Output:
        """output <source> -> console | file "<path>" | Here[(<threshold>)]"""
        self._consume('KW', 'output')
        source = self._consume('ID').value
        self._consume('ARROW')
        tok = self._peek()
        if tok.kind == 'KW' and tok.value == 'console':
            self._consume('KW', 'console')
            return Output(source, 'console')
        if tok.kind == 'KW' and tok.value == 'file':
            self._consume('KW', 'file')
            path = self._consume('STRING').value
            return Output(source, 'file', path=path)
        if tok.kind == 'KW' and tok.value == 'Here':
            self._consume('KW', 'Here')
            threshold = self._parse_opt_threshold()
            return Output(source, 'database', threshold=threshold)
        raise ParseError(
            f"Expected output target (console / file / Here), "
            f"got {tok.kind!r} ({tok.value!r}) at pos {tok.pos}"
        )

    # ── newTable ────────────────────────────────────────────────────────────

    def _parse_new_table(self) -> NewTable:
        """newTable "<name>" [from <source>] [addColumns [<items>]]"""
        self._consume('KW', 'newTable')
        name = self._consume('STRING').value

        source: Optional[str] = None
        if self._is('KW', 'from'):
            self._consume('KW', 'from')
            source = self._consume('ID').value

        columns: list = []
        if self._is('KW', 'addColumns'):
            self._consume('KW', 'addColumns')
            self._consume('LBRACKET')
            columns = self._parse_column_func_list()
            self._consume('RBRACKET')

        return NewTable(name, source, columns)

    def _parse_column_func_list(self) -> list:
        """
        <columnfunc> ::= <string> | <identifier> | <funccall>

        Each item is one of:
          • Literal(str)   — a quoted column name, e.g. "email"
          • Variable       — a bare identifier referencing a meta-column,
                             e.g.  duplicate_score
          • FunctionCall   — e.g.  length("name")
        """
        items: list = []
        while not self._is('RBRACKET'):
            tok = self._peek()
            if tok.kind == 'STRING':
                items.append(Literal(self._consume('STRING').value))
            elif tok.kind == 'ID':
                if self._is('LPAREN', offset=1):
                    items.append(self._parse_function_call())
                else:
                    items.append(Variable(self._consume('ID').value))
            else:
                raise ParseError(
                    f"Expected column name (STRING / ID) or function call "
                    f"in addColumns, got {tok.kind!r} ({tok.value!r}) "
                    f"at pos {tok.pos}"
                )
            if self._is('COMMA'):
                self._consume('COMMA')
        return items

    # ── function call ───────────────────────────────────────────────────────

    def _parse_function_call(self) -> FunctionCall:
        """<identifier> '(' [<arglist>] ')'"""
        name = self._consume('ID').value
        self._consume('LPAREN')
        args: list = []
        while not self._is('RPAREN'):
            args.append(self._parse_value_node())
            if self._is('COMMA'):
                self._consume('COMMA')
        self._consume('RPAREN')
        return FunctionCall(name, args)

    # ── terminal value ──────────────────────────────────────────────────────

    def _parse_value_node(self) -> ASTNode:
        """
        <value> ::= <identifier> [ '(' <arglist> ')' ]
                  | <string>
                  | <number>

        Identifiers that are immediately followed by '(' are parsed as
        function calls (handles nested calls inside expressions and addColumns).
        """
        tok = self._peek()
        if tok.kind == 'ID':
            if self._is('LPAREN', offset=1):
                return self._parse_function_call()
            return Variable(self._consume('ID').value)
        if tok.kind == 'STRING':
            return Literal(self._consume('STRING').value)
        if tok.kind == 'NUMBER':
            return Literal(self._consume('NUMBER').value)
        raise ParseError(
            f"Expected a value (ID / STRING / NUMBER), "
            f"got {tok.kind!r} ({tok.value!r}) at pos {tok.pos}"
        )


# ═══════════════════════════════════════════════════════════════════════════
#  4.  AST PRETTY-PRINTER
# ═══════════════════════════════════════════════════════════════════════════

def print_ast(node: ASTNode, indent: int = 0) -> None:
    pad = '  ' * indent

    if isinstance(node, Program):
        print('DaQuVa AST')
        print('══════════')
        for s in node.statements:
            print_ast(s, indent + 1)

    elif isinstance(node, DatabaseInit):
        print(f'{pad}DatabaseInit: "{node.connection}"')

    elif isinstance(node, FunctionDef):
        params = ', '.join(node.params)
        print(f'{pad}FunctionDef {node.name}({params}):')
        for s in node.body:
            print_ast(s, indent + 1)
        print(f'{pad}end')

    elif isinstance(node, Assignment):
        print(f'{pad}Assignment {node.name} =')
        print_ast(node.value, indent + 1)

    elif isinstance(node, ReturnStatement):
        print(f'{pad}Return:')
        print_ast(node.value, indent + 1)

    elif isinstance(node, Scan):
        tbl = (f'"{node.table.value}"' if isinstance(node.table, Literal)
               else node.table.name)
        print(f'{pad}Scan {tbl}."{node.column}" using tool "{node.tool}"')

    elif isinstance(node, Filter):
        print(f'{pad}Filter {node.source} where:')
        print_ast(node.condition, indent + 1)

    elif isinstance(node, FindDuplicates):
        cols = ', '.join(f'"{c}"' for c in node.columns)
        tool_str = f' using tool "{node.tool}"' if node.tool else ' (no tool)'
        print(f'{pad}FindDuplicates {node.source} columns [{cols}]{tool_str}')

    elif isinstance(node, Merge):
        thr = f'({node.threshold})' if node.threshold is not None else '(default)'
        print(f'{pad}Merge {node.source} -> Here{thr} allowDanger')

    elif isinstance(node, Output):
        if node.target == 'console':
            print(f'{pad}Output {node.source} -> console')
        elif node.target == 'file':
            print(f'{pad}Output {node.source} -> file "{node.path}"')
        else:
            thr = f'({node.threshold})' if node.threshold is not None else ''
            print(f'{pad}Output {node.source} -> Here{thr} [database]')

    elif isinstance(node, NewTable):
        src = f' from {node.source}' if node.source else ''
        print(f'{pad}NewTable "{node.name}"{src}')
        if node.columns:
            print(f'{pad}  addColumns:')
            for col in node.columns:
                print_ast(col, indent + 2)

    elif isinstance(node, BinaryOp):
        print(f'{pad}BinaryOp [{node.op}]:')
        print_ast(node.left,  indent + 1)
        print_ast(node.right, indent + 1)

    elif isinstance(node, FunctionCall):
        print(f'{pad}FunctionCall {node.name}(')
        for a in node.args:
            print_ast(a, indent + 1)
        print(f'{pad})')

    elif isinstance(node, Variable):
        print(f'{pad}Variable {node.name}')

    elif isinstance(node, Literal):
        if isinstance(node.value, str):
            print(f'{pad}Literal "{node.value}"')
        else:
            print(f'{pad}Literal {node.value}')

    else:
        print(f'{pad}[Unknown node: {node!r}]')


# ═══════════════════════════════════════════════════════════════════════════
#  5.  TESTS
# ═══════════════════════════════════════════════════════════════════════════

# ── Test 1: canonical example from §2.4 of the DaQuVa specification ────────

SPEC_EXAMPLE = r"""
# === 1. Database connection ===
my db "someconnectionstringgoeshere";

# === 2. Reusable function: clean emails in any table ===
function cleanEmails(tablename, threshold):
    # Scan the email column with an AI validator
    potentialdirty = scan tablename."email" using tool "misaaivalidator";
    # Keep only rows whose dirty_level exceeds the threshold
    highrisk = filter potentialdirty where dirtylevel > threshold;
    return highrisk;
end

# === 3. Apply the function to the "users" table ===
highriskeamils = cleanEmails("users", 70);

# === 4. Export results ===
output highriskeamils -> file "highriskeamils.csv";
output highriskeamils -> console;

# === 5. Detect near-duplicate records among high-risk rows ===
duplicates = findLocalDuplicates highriskeamils columns ["name", "dob"] using tool "fuzzymatcher";

# === 6. Merge duplicates back into the database (confidence >= 90%) ===
merge duplicates -> here(90) allowDanger;

# === 7. Create a summary table for downstream analysis ===
analysistable = newTable "highriskanalysis"
    from highriskeamils
    addColumns [duplicatescore, length("name")];

# === 8. Additional validation pass on the summary table ===
cliresult = scan analysistable."email" using tool "typochecker";
output cliresult -> console;
"""

# ── Test 2: extended coverage — all optional clauses, bare commands ─────────

EXTENDED_EXAMPLE = r"""
# Minimal database init
my db "postgres://localhost/mydb";

# newTable — no from, no addColumns
emptyresult = newTable "staging";

# newTable — only addColumns, no from
withcols = newTable "derived" addColumns ["col1", "col2"];

# output -> Here without a threshold
output emptyresult -> Here;

# output -> Here with a threshold
output withcols -> Here(80);

# findLocalDuplicates — no using tool
dupes = findLocalDuplicates emptyresult columns ["id", "email"];

# merge — no threshold (Here without parentheses)
merge dupes -> Here allowDanger;

# function with multiple AND/OR conditions in filter
function scoreCheck(data):
    result = filter data where score > 50 AND status == "active" OR flag != 0;
    return result;
end

cleaned = scoreCheck(emptyresult);
output cleaned -> console;
"""


def run_test(name: str, source: str) -> bool:
    print(f'\n{"─" * 60}')
    print(f'TEST: {name}')
    print('─' * 60)
    try:
        lexer  = Lexer(source)
        parser = Parser(lexer)
        ast    = parser.parse()
        print_ast(ast)
        print(f'\n✓  {name} PASSED\n')
        return True
    except (LexerError, SyntaxError) as exc:
        print(f'\n✗  {name} FAILED: {exc}\n')
        return False


if __name__ == '__main__':
    results = [
        run_test('§2.4 Spec Example',    SPEC_EXAMPLE),
        run_test('Extended Coverage',    EXTENDED_EXAMPLE),
    ]
    passed = sum(results)
    total  = len(results)
    print(f'{"═" * 60}')
    print(f'Results: {passed}/{total} tests passed')
    print('═' * 60)