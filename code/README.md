# DaQuVa

DaQuVa means **Data Query Validation**. It is a small Python DSL for validating and transforming tabular data from CSV and SQLite sources.

DaQuVa is not an ORM and it is not an in-memory dataframe engine. Table variables store lazy logical relational plans. Rows are fetched only when a program asks for materialization through console output, CSV output, or SQLite save/output.

```text
DaQuVa source
  -> Lexer
  -> Parser
  -> AST
  -> Logical relational plan
  -> Execution engine
  -> SQL / CSV operations
```

## Current Features

- SQLite and CSV connections
- lazy `scan`
- lazy `filter` with compound `AND` / `OR` conditions (`AND` binds tighter than `OR`)
- string predicates `starts_with`, `contains`, `ends_with`
- result-set ordering with `sort` and row capping with `limit`
- CSV output
- SQLite output/save
- simple row and column edits
- fuzzy duplicate detection (also available as the `levenshtein_matcher` alias)
- typo detection with deterministic Levenshtein/domain heuristics
- duplicate-aware `merge`, valid only after `find_duplicates`
- `summarize`, an aggregate proof table of row counts per pipeline stage
- SQL pushdown for simple SQLite scan/filter/project/sort/limit chains
- Python execution for semantic tools such as typo and duplicate detection
- an interactive REPL (`--repl`) for incremental, statement-by-statement use

Future ideas such as joins, relation restoration, causal inference, distributed execution, and advanced optimization are intentionally out of scope for this MVP.

## Lazy Plans

This DaQuVa program:

```dqv
sqlite main "users.db";

users = scan main.users;
adults = filter users where age >= 18;
names = filter adults where name starts_with "J";
names -> file "output/names.csv";
```

does not copy table rows into `users`, `adults`, or `names`. Internally it builds a plan shaped like this:

```text
Filter(name starts_with "J")
  -> Filter(age >= 18)
     -> Source(main.users)
```

The execution engine evaluates the plan only when `names -> file ...` runs.

## Project Structure

```text
daquva/
  lexer.py
  parser.py
  ast_nodes.py
  runtime.py
  execution_engine.py
  table.py
  cli.py
  repl.py
  tools/
    fuzzy_duplicates.py
    typo_detector.py
  outputs/
    csv_output.py
    sqlite_output.py
  connections/
    sqlite_connection.py
    csv_connection.py
  utils/
    pretty_print.py

demo/
  demo_01_basic_scan/
  demo_02_filter/
  demo_03_duplicates/
  demo_04_csv_output/
  demo_05_sqlite_output/
  demo_06_pipeline/
  demo_07_multiple_sources/
  demo_08_functions/
  demo_showcase/

present.ps1
```

The parser only creates AST nodes. `Table` only stores immutable logical plans and schema metadata. `ExecutionEngine` is the only layer that fetches rows.

## Install uv

Windows PowerShell:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
uv python install 3.14
uv sync
```

macOS:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv python install 3.14
uv sync
```

Linux:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv python install 3.14
uv sync
```

This project has no third-party runtime dependencies; `uv` still manages the project environment and lockfile.

## Run DaQuVa

Run any `.dqv` file with:

```bash
uv run python -m daquva path/to/program.dqv
```

Print tokens or the parsed AST:

```bash
uv run python -m daquva path/to/program.dqv --tokens
uv run python -m daquva path/to/program.dqv --ast
```

You can also call the compatibility entry file:

```bash
uv run python main.py path/to/program.dqv
```

## Interactive REPL

Start a persistent session (omit the file, or pass `--repl`):

```bash
uv run python -m daquva --repl
```

The REPL keeps one runtime context, so you can declare connections, assign
intermediate tables, and print results without rerunning a whole script. After
each assignment it reports the variable name, row count, column count, and column
names. Meta-commands:

- `:help` — list available commands
- `:tables` — list active connections
- `:vars` — list in-memory variables and their schemas
- `:quit` — exit the session

## Run Demos

Each demo contains a `.dqv` source file, input data, expected CSV outputs, and a README.

```bash
uv run python -m daquva demo/demo_01_basic_scan/basic_scan.dqv
uv run python -m daquva demo/demo_02_filter/filter.dqv
uv run python -m daquva demo/demo_03_duplicates/duplicates.dqv
uv run python -m daquva demo/demo_04_csv_output/csv_output.dqv
uv run python -m daquva demo/demo_05_sqlite_output/sqlite_output.dqv
uv run python -m daquva demo/demo_06_pipeline/pipeline.dqv
uv run python -m daquva demo/demo_07_multiple_sources/multiple_sources.dqv
uv run python -m daquva demo/demo_08_functions/functions_pipeline.dqv
uv run python -m daquva demo/demo_showcase/showcase.dqv
```

Generated files go into each demo's `output/` directory. Expected CSV files live in each demo's `expected/` directory.

`demo_showcase` is the end-to-end headline demo: it exercises every major feature
(scan + typo detection, compound `AND`/`OR` filters, `contains`/`ends_with`,
`sort`/`limit`, fuzzy duplicates, `merge`, CSV + SQLite output, and the
`summarize` proof table) over a 30-row dataset. See `demo/demo_showcase/README.md`.

## Live Demo Driver

`present.ps1` (PowerShell, run from `code/`) walks through the whole pipeline with
a pause before each step — source, lexer tokens, parsed AST, execution, the
CSV/SQLite proof artifacts, and an optional REPL session. It auto-detects `uv` and
falls back to plain `python`.

```powershell
.\present.ps1
```

## CSV and SQLite Output

CSV output:

```dqv
users -> file "output/users.csv";
```

SQLite save:

```dqv
sqlite out "output/result.sqlite";
save users into result_table allowDanger;
```

Without `allowDanger`, DaQuVa refuses to overwrite an existing SQLite table. With `allowDanger`, the output table is dropped and recreated.

`save` writes to a SQLite connection named `out` or `output` when present. Otherwise, it uses the last SQLite connection declared in the program.

## Duplicate Merge Semantics

`merge` is intentionally narrow. It only accepts a table produced by `find_duplicates`:

```dqv
dupes = find_duplicates users[name] using tool fuzzy_duplicates(2);
merged = merge dupes;
```

Duplicate detection adds logical metadata columns such as:

- `duplicate_group_id`
- `similarity_score`
- `canonical_candidate`
- `matched_with`

`merge` consumes those metadata columns, consolidates duplicate groups, and produces a new lazy table plan. This is invalid and raises a runtime error:

```dqv
merged = merge users;
```

## Aggregate Proof Summary

`summarize` takes one or more previously bound tables (the stages of a pipeline)
and produces one row of metrics per stage. Unlike every other command it does not
add columns to the data; it reduces each stage to a fixed schema of counts, giving
an inspectable proof that a transformation happened:

```dqv
proof = summarize raw, paid_adults, dupes, merged;
proof -> file "output/proof_summary.csv";
save proof into proof_summary allowDanger;
```

The result columns are `stage`, `row_count`, `column_count`,
`duplicate_group_count`, `duplicate_candidate_count`, `typo_suspect_count`,
`input_rows_represented`, and `rows_removed_by_merge`. The last two are derived
from the `merged_from_count` annotation, so a merge that collapses several input
rows into one is reported as rows represented versus rows removed. Because the
summary is an ordinary result set, it can be written to CSV or SQLite like any
other table.

## Example Program

```dqv
csv people "input/people.csv";
sqlite out "output/people.sqlite";

people = scan people.people using_tool typo_detector("email");
adults = filter people where age >= 18;
dupes = find_duplicates adults[name] using tool fuzzy_duplicates(2);
cleaned = merge dupes;

people -> file "output/typo_analysis.csv";
cleaned -> file "output/cleaned_people.csv";
save cleaned into cleaned_people allowDanger;
```

The tool-generated columns are logical metadata columns. They can exist only during execution or be materialized when output/save is requested.
