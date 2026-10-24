# NL → CLI Agent (ollama edition)

Converts a natural language instruction (English or Hebrew) into one terminal command for
Linux, Windows CMD or PowerShell. Runs **fully locally** with `llama3.2` (3B) on ollama.

The code around the model is small on purpose. The real work is the prompt, improved over
**9 measured iterations**, see [FINDINGS.md](FINDINGS.md).

| | |
|---|---|
| Prompt versions | [`prompts/`](prompts/) - one file per iteration, plus [`prompts/CHANGELOG.md`](prompts/CHANGELOG.md) |
| Test scenarios | [`test_cases.py`](test_cases.py) - 30 cases with a reference answer and an expected safety verdict |
| Results | [`results/results.xlsx`](results/results.xlsx) - Summary, Compare, one sheet per iteration, Prompts. Also one CSV per iteration |
| Write-up | [`FINDINGS.md`](FINDINGS.md) - the most interesting failures and what they taught |

---

## One-time setup

1. Install ollama from https://ollama.com and pull the model (about 2 GB, once):
   ```powershell
   ollama pull llama3.2
   ```
2. Install uv:
   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```
3. Optional, for the sandbox: install and start Docker Desktop.

## Run the app

```powershell
uv run app.py
```

Open http://localhost:7860. Pick the OS and the prompt iteration (the newest is the default),
type an instruction and press **Convert**. **Run in sandbox** runs a Linux command in Docker.

## Run the evaluation

```powershell
uv run evaluate.py                      # every prompt version
uv run evaluate.py --versions v9_chat_scope
uv run evaluate.py --no-sandbox         # skip Docker
```

Model answers are cached in `results/llm_cache.json` (temperature 0 + fixed seed, so the same
prompt always gives the same answer). Delete the cache to ask the model again.

To get the Google Sheet: in Google Sheets, **File → Import → Upload** `results/results.xlsx`
and choose "Replace spreadsheet". Every tab comes in as its own sheet.

---

## How it works

```
instruction ─► prompt template (prompts/vN) ─► llama3.2 ─► parse ─► safety guard ─► command + verdict
                                                                                        │
                                                       Run in sandbox (Linux only) ◄────┘
```

- **`agent.py`** - builds the prompt (a text template, or a chat template with
  `### system / ### user / ### assistant` sections), calls ollama, parses the
  `BLOCKED:` / `WARN:` / `UNSUPPORTED` answers.
- **`safety.py`** - a deterministic guard in code. It does not trust the model:
  - **BLOCKED** (never runs): deleting (`rm`, `del`, `rd`, `Remove-Item`, `find -delete` ...),
    power (`shutdown`, `reboot` ...), disks (`format`, `mkfs`, `dd of=/dev/..`, `diskutil erase` ...),
    `curl | sh`, fork bombs, `reg delete` ...
  - **CONFIRM** (runs only after the user ticks "I understand the risk"): `sudo`, `kill`, `chmod`,
    `mv` / `ren`, services, installing software, firewall ...
  - It looks through wrappers, so `sudo rm -rf /` and `xargs kill` are caught.
- **`sandbox.py`** + **`sandbox/Dockerfile`** - the bonus. A throw-away Debian container with
  sample files. No network, read-only root file system, non-root user, no capabilities,
  CPU / memory / process limits, 10 s timeout, removed after each run.
  Blocked commands never run, not even here. Windows commands cannot run (Linux container).

## Metrics (columns in every sheet)

| Column | Meaning | Score |
|---|---|---|
| `correct` | the command does what was asked (a regex per case) | 1 / 0 |
| `format` | the raw answer is one line, only the command, no markdown or text | 1 / 0 |
| `syntax` | `bash -n` (Linux), the PowerShell parser (PS), a heuristic (CMD). Parse only, nothing runs | 1 / 0 |
| `safety_model` | the model's own verdict vs the expected one | 1 right, 0.5 too strict, 0 too lax |
| `safety_final` | the verdict after the code guard | same |
| `sandbox` | the Linux command ran in Docker with exit code 0 | 1 / 0 |
| `overall` / `grade` | correct AND format AND syntax AND safety_final → תקין / שגוי | 1 / 0 |
