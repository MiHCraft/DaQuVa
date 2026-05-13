"""Recursive descent parser for DaQuVa.

This parser intentionally stops at AST generation. It does not inspect files,
open databases, or execute tools.
"""

from __future__ import annotations

from daquva.ast_nodes import (
    AddColumnsExpression,
    AddRowsExpression,
    Assignment,
    Condition,
    ConnectionDecl,
    DeleteColumnsExpression,
    DeleteRowsExpression,
    EditRowsExpression,
    FilterExpression,
    FindDuplicatesExpression,
    FunctionCall,
    FunctionDefinition,
    Literal,
    MergeExpression,
    OutputDestination,
    OutputStatement,
    Program,
    RenameColumnExpression,
    ReturnStatement,
    SaveStatement,
    ScanExpression,
    TableReference,
    ValueNode,
    VariableReference,
)
from daquva.lexer import Token, TokenType


class Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.index = 0

    def parse(self) -> Program:
        connections: list[ConnectionDecl] = []
        statements: list[object] = []

        while self._peek().type in {TokenType.SQLITE, TokenType.CSV}:
            connections.append(self._connection())

        while self._peek().type != TokenType.EOF:
            if self._match(TokenType.SEMICOLON):
                continue
            statements.append(self._statement())
            self._expect(TokenType.SEMICOLON)

        return Program(tuple(connections), tuple(statements))

    def _connection(self) -> ConnectionDecl:
        kind_token = self._advance()
        name = self._expect(TokenType.IDENTIFIER).value
        path = self._expect(TokenType.STRING).value
        self._expect(TokenType.SEMICOLON)
        return ConnectionDecl(str(kind_token.value), str(name), str(path))

    def _statement(self) -> object:
        if self._looks_like_function_definition():
            return self._function_definition()

        if self._peek().type == TokenType.OUTPUT:
            self._advance()
            return self._output_expression()

        if self._peek().type == TokenType.IDENTIFIER and self._peek_next().type == TokenType.ASSIGN:
            target = str(self._advance().value)
            self._expect(TokenType.ASSIGN)
            return Assignment(target, self._command_expression())

        return self._command_expression()

    def _looks_like_function_definition(self) -> bool:
        if not (
            self._peek().type == TokenType.IDENTIFIER
            and self._peek_next().type == TokenType.LPAREN
        ):
            return False
        cursor = self.index + 2
        depth = 1
        while cursor < len(self.tokens):
            token_type = self.tokens[cursor].type
            if token_type == TokenType.LPAREN:
                depth += 1
            elif token_type == TokenType.RPAREN:
                depth -= 1
                if depth == 0:
                    return (
                        cursor + 1 < len(self.tokens)
                        and self.tokens[cursor + 1].type == TokenType.LBRACE
                    )
            cursor += 1
        return False

    def _command_expression(self) -> object:
        token_type = self._peek().type

        if token_type == TokenType.SCAN:
            return self._scan_expression()
        if token_type == TokenType.FILTER:
            return self._filter_expression()
        if token_type == TokenType.FIND_DUPLICATES:
            return self._find_duplicates_expression()
        if token_type == TokenType.MERGE:
            return self._merge_expression()
        if token_type == TokenType.SAVE:
            return self._save_expression()
        if token_type == TokenType.ADD_ROWS:
            return self._add_rows_expression()
        if token_type == TokenType.ADD_COLUMNS:
            return self._add_columns_expression()
        if token_type == TokenType.EDIT_ROWS:
            return self._edit_rows_expression()
        if token_type == TokenType.EDIT_COLUMNS:
            return self._rename_column_expression()
        if token_type == TokenType.DELETE_COLUMNS:
            return self._delete_columns_expression()
        if token_type == TokenType.DELETE_ROWS:
            return self._delete_rows_expression()

        if token_type in {
            TokenType.IDENTIFIER,
            TokenType.STRING,
            TokenType.NUMBER,
            TokenType.TRUE,
            TokenType.FALSE,
        }:
            if token_type == TokenType.IDENTIFIER and self._peek_next().type == TokenType.LPAREN:
                return self._function_call()
            value = self._value_or_variable()
            if self._peek().type == TokenType.ARROW:
                return self._output_expression(value)
            return value

        self._raise(f"Unexpected token {self._peek().type.name}")

    def _scan_expression(self) -> ScanExpression:
        self._expect(TokenType.SCAN)
        source = self._table_reference()
        tool = None
        params: tuple[ValueNode, ...] = ()

        if self._match(TokenType.USING_TOOL):
            tool = self._expect(TokenType.IDENTIFIER).value
            params = self._optional_param_list()

        return ScanExpression(source, str(tool) if tool else None, params)

    def _filter_expression(self) -> FilterExpression:
        self._expect(TokenType.FILTER)
        source = self._table_reference()
        self._expect(TokenType.WHERE)
        return FilterExpression(source, self._condition())

    def _find_duplicates_expression(self) -> FindDuplicatesExpression:
        self._expect(TokenType.FIND_DUPLICATES)
        source = self._table_reference()
        self._expect(TokenType.USING)
        self._expect(TokenType.TOOL)
        tool = self._expect(TokenType.IDENTIFIER).value
        return FindDuplicatesExpression(source, str(tool), self._optional_param_list())

    def _merge_expression(self) -> MergeExpression:
        self._expect(TokenType.MERGE)
        return MergeExpression(str(self._expect(TokenType.IDENTIFIER).value))

    def _save_expression(self) -> SaveStatement:
        self._expect(TokenType.SAVE)
        source = self._table_reference()
        self._expect(TokenType.INTO)
        table_name = str(self._expect(TokenType.IDENTIFIER).value)
        allow_danger = self._match(TokenType.ALLOW_DANGER)
        return SaveStatement(source, table_name, allow_danger)

    def _add_rows_expression(self) -> AddRowsExpression:
        self._expect(TokenType.ADD_ROWS)
        source_name = str(self._expect(TokenType.IDENTIFIER).value)
        self._expect(TokenType.LPAREN)
        values = self._value_list_until(TokenType.RPAREN)
        self._expect(TokenType.RPAREN)
        return AddRowsExpression(source_name, values)

    def _add_columns_expression(self) -> AddColumnsExpression:
        self._expect(TokenType.ADD_COLUMNS)
        source_name = str(self._expect(TokenType.IDENTIFIER).value)
        columns: list[tuple[str, str]] = []

        while True:
            name = str(self._expect(TokenType.IDENTIFIER).value)
            self._expect(TokenType.COLON)
            type_token = self._advance()
            if type_token.type not in {
                TokenType.NUMBER_TYPE,
                TokenType.STRING_TYPE,
                TokenType.BOOL_TYPE,
                TokenType.TABLE_TYPE,
            }:
                self._raise("Expected column type")
            columns.append((name, str(type_token.value)))
            if not self._match(TokenType.COMMA):
                break

        return AddColumnsExpression(source_name, tuple(columns))

    def _edit_rows_expression(self) -> EditRowsExpression:
        self._expect(TokenType.EDIT_ROWS)
        source_name = str(self._expect(TokenType.IDENTIFIER).value)
        self._expect(TokenType.WHERE)
        condition = self._condition()
        self._expect(TokenType.SET)
        assignments: list[tuple[str, ValueNode]] = []

        while True:
            column = str(self._expect(TokenType.IDENTIFIER).value)
            self._expect(TokenType.ASSIGN)
            assignments.append((column, self._value_or_variable()))
            if not self._match(TokenType.COMMA):
                break

        return EditRowsExpression(source_name, condition, tuple(assignments))

    def _rename_column_expression(self) -> RenameColumnExpression:
        self._expect(TokenType.EDIT_COLUMNS)
        source_name = str(self._expect(TokenType.IDENTIFIER).value)
        self._expect(TokenType.RENAME)
        old_name = str(self._expect(TokenType.IDENTIFIER).value)
        self._expect(TokenType.TO)
        new_name = str(self._expect(TokenType.IDENTIFIER).value)
        return RenameColumnExpression(source_name, old_name, new_name)

    def _delete_columns_expression(self) -> DeleteColumnsExpression:
        self._expect(TokenType.DELETE_COLUMNS)
        source_name = str(self._expect(TokenType.IDENTIFIER).value)
        self._expect(TokenType.LBRACKET)
        columns = self._identifier_list_until(TokenType.RBRACKET)
        self._expect(TokenType.RBRACKET)
        return DeleteColumnsExpression(source_name, columns)

    def _delete_rows_expression(self) -> DeleteRowsExpression:
        self._expect(TokenType.DELETE_ROWS)
        source_name = str(self._expect(TokenType.IDENTIFIER).value)
        self._expect(TokenType.WHERE)
        return DeleteRowsExpression(source_name, self._condition())

    def _output_expression(self, value: ValueNode | None = None) -> OutputStatement:
        if value is None:
            value = self._value_or_variable()
        self._expect(TokenType.ARROW)

        if self._match(TokenType.CONSOLE):
            destination = OutputDestination("console")
        elif self._match(TokenType.FILE):
            destination = OutputDestination("file", str(self._expect(TokenType.STRING).value))
        elif self._match(TokenType.DATABASE):
            destination = OutputDestination("database", str(self._expect(TokenType.IDENTIFIER).value))
        else:
            self._raise("Expected output destination: console, file, or database")

        return OutputStatement(value, destination)

    def _function_definition(self) -> FunctionDefinition:
        name = str(self._expect(TokenType.IDENTIFIER).value)
        self._expect(TokenType.LPAREN)
        params = self._identifier_list_until(TokenType.RPAREN)
        self._expect(TokenType.RPAREN)
        self._expect(TokenType.LBRACE)

        body: list[object] = []
        while self._peek().type != TokenType.RBRACE:
            if self._match(TokenType.SEMICOLON):
                continue
            if self._match(TokenType.RETURN):
                body.append(ReturnStatement(self._value_or_variable()))
            else:
                body.append(self._statement())
            self._expect(TokenType.SEMICOLON)

        self._expect(TokenType.RBRACE)
        return FunctionDefinition(name, params, tuple(body))

    def _function_call(self) -> FunctionCall:
        name = str(self._expect(TokenType.IDENTIFIER).value)
        self._expect(TokenType.LPAREN)
        args = self._value_list_until(TokenType.RPAREN)
        self._expect(TokenType.RPAREN)
        return FunctionCall(name, args)

    def _table_reference(self) -> TableReference:
        first = str(self._expect(TokenType.IDENTIFIER).value)
        connection = None
        name = first

        if self._match(TokenType.DOT):
            connection = first
            name = str(self._expect(TokenType.IDENTIFIER).value)

        columns: tuple[str, ...] = ()
        if self._match(TokenType.LBRACKET):
            columns = self._identifier_list_until(TokenType.RBRACKET)
            self._expect(TokenType.RBRACKET)

        return TableReference(name=name, connection=connection, columns=columns)

    def _condition(self) -> Condition:
        column = str(self._expect(TokenType.IDENTIFIER).value)

        if self._match(TokenType.STARTS_WITH):
            return Condition(column, "starts_with", self._value_or_variable())

        operator_token = self._advance()
        operator_by_type = {
            TokenType.EQ: "==",
            TokenType.NE: "!=",
            TokenType.LT: "<",
            TokenType.GT: ">",
            TokenType.LE: "<=",
            TokenType.GE: ">=",
        }
        if operator_token.type not in operator_by_type:
            self._raise("Expected comparison operator")

        return Condition(column, operator_by_type[operator_token.type], self._value_or_variable())

    def _optional_param_list(self) -> tuple[ValueNode, ...]:
        if not self._match(TokenType.LPAREN):
            return ()
        values = self._value_list_until(TokenType.RPAREN)
        self._expect(TokenType.RPAREN)
        return values

    def _value_list_until(self, end_token: TokenType) -> tuple[ValueNode, ...]:
        values: list[ValueNode] = []
        if self._peek().type == end_token:
            return ()

        while True:
            values.append(self._value_or_variable())
            if self._peek().type == end_token:
                break
            self._expect(TokenType.COMMA)

        return tuple(values)

    def _identifier_list_until(self, end_token: TokenType) -> tuple[str, ...]:
        names: list[str] = []
        if self._peek().type == end_token:
            return ()

        while True:
            names.append(str(self._expect(TokenType.IDENTIFIER).value))
            if self._peek().type == end_token:
                break
            self._expect(TokenType.COMMA)

        return tuple(names)

    def _value_or_variable(self) -> ValueNode:
        token = self._advance()
        if token.type == TokenType.STRING:
            return Literal(token.value)
        if token.type == TokenType.NUMBER:
            return Literal(token.value)
        if token.type == TokenType.TRUE:
            return Literal(True)
        if token.type == TokenType.FALSE:
            return Literal(False)
        if token.type == TokenType.IDENTIFIER:
            return VariableReference(str(token.value))
        self._raise("Expected value or variable")

    def _match(self, token_type: TokenType) -> bool:
        if self._peek().type == token_type:
            self._advance()
            return True
        return False

    def _expect(self, token_type: TokenType) -> Token:
        token = self._peek()
        if token.type != token_type:
            self._raise(f"Expected {token_type.name}, got {token.type.name}")
        return self._advance()

    def _advance(self) -> Token:
        token = self.tokens[self.index]
        self.index += 1
        return token

    def _peek(self) -> Token:
        return self.tokens[self.index]

    def _peek_next(self) -> Token:
        if self.index + 1 >= len(self.tokens):
            return self.tokens[-1]
        return self.tokens[self.index + 1]

    def _raise(self, message: str) -> None:
        token = self._peek()
        raise SyntaxError(f"{message} at line {token.line}, column {token.column}")
