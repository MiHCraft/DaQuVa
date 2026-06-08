# ================================================================
#  DaQuVa live presentation driver
#  Run from the code/ directory:   .\present.ps1
#  Walks through the whole DSL end-to-end with a pause before each step.
# ================================================================

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# Use `uv run python` if uv is installed, otherwise plain python.
if (Get-Command uv -ErrorAction SilentlyContinue) {
    $PY    = "uv"
    $PYARG = @("run", "python")
} else {
    $PY    = "python"
    $PYARG = @()
}

function PyRun { param([string[]]$Rest) & $PY @($PYARG + $Rest) }

function Step($title) {
    Write-Host ""
    Write-Host ("=" * 70) -ForegroundColor DarkCyan
    Write-Host "  $title" -ForegroundColor Cyan
    Write-Host ("=" * 70) -ForegroundColor DarkCyan
    Read-Host "  (press Enter to run this step)" | Out-Null
}

$SHOWCASE = "demo/demo_showcase/showcase.dqv"

Clear-Host
Write-Host "DaQuVa - Data Quality Validation DSL" -ForegroundColor Green
Write-Host "Pipeline:  source -> Lexer -> Parser -> AST -> logical plan -> execution (CSV/SQLite)"

# ---- 1. The program we are about to run ------------------------
Step "1/6  The DaQuVa program (showcase.dqv)"
Get-Content $SHOWCASE

# ---- 2. Lexer: it is a real language, not string hacks ---------
Step "2/6  Lexer -> token stream (first 25 tokens)"
PyRun @("-c", @"
from pathlib import Path
from daquva.lexer import Lexer
toks = Lexer(Path('$SHOWCASE').read_text(encoding='utf-8')).tokenize()
for t in toks[:25]:
    print(t)
print(f'... {len(toks)} tokens total')
"@)

# ---- 3. Parser -> AST (structure, without executing) -----------
Step "3/6  Parser -> AST (one node per statement, no execution yet)"
PyRun @("-c", @"
from pathlib import Path
from daquva.lexer import Lexer
from daquva.parser import Parser
prog = Parser(Lexer(Path('$SHOWCASE').read_text(encoding='utf-8')).tokenize()).parse()
print(f'connections: {len(prog.connections)}   statements: {len(prog.statements)}')
for s in prog.statements:
    print('  -', type(s).__name__, repr(s)[:88])
"@)

# ---- 4. Execute the whole pipeline -----------------------------
Step "4/6  Execute: scan/typo, AND/OR filters, sort/limit, duplicates, merge, summarize"
PyRun @("-m", "daquva", $SHOWCASE)

# ---- 5. Proof it happened: artifacts on disk -------------------
Step "5/6  Proof artifacts (CSV + SQLite)"
Write-Host "--- output/proof_summary.csv ---" -ForegroundColor Yellow
Get-Content "demo/demo_showcase/output/proof_summary.csv"
Write-Host ""
Write-Host "--- SQLite tables in output/showcase.sqlite ---" -ForegroundColor Yellow
PyRun @("-c", @"
import sqlite3
c = sqlite3.connect('demo/demo_showcase/output/showcase.sqlite')
for name, typ in c.execute('select name, type from sqlite_master').fetchall():
    if typ == 'table':
        n = c.execute('select count(*) from ' + name).fetchone()[0]
        print('  ' + name + ': ' + str(n) + ' rows')
"@)

# ---- 6. Interactive REPL (optional, live) ----------------------
Step "6/6  Interactive REPL (optional) -- try :vars then :quit to finish"
PyRun @("-m", "daquva", "--repl")

Write-Host ""
Write-Host "Presentation complete." -ForegroundColor Green
