"""The agent: natural language in, one CLI command out.

The prompt templates live in prompts/ (one file per iteration). A template has
two placeholders: {os_target} and {instruction}.

A template is either one block of text (sent to /api/generate), or a chat made
of "### system" / "### user" / "### assistant" sections (sent to /api/chat).
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

import requests

import safety

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_CHAT_URL = "http://localhost:11434/api/chat"
MODEL = "llama3.2"
# temperature 0 + fixed seed, so the same prompt gives the same answer and
# iterations can be compared fairly
MODEL_OPTIONS = {"temperature": 0, "seed": 42}

PROMPTS_DIR = Path(__file__).parent / "prompts"
OS_TARGETS = ["Linux / macOS", "Windows (CMD)", "PowerShell"]

UNSUPPORTED = "UNSUPPORTED"


def load_prompts() -> dict[str, str]:
    """{"v1_basic": "<template>", ...} ordered by version."""
    return {p.stem: p.read_text(encoding="utf-8") for p in sorted(PROMPTS_DIR.glob("v*.txt"))}


_CHAT_ROLE = re.compile(r"^### (system|user|assistant)[ \t]*$", re.MULTILINE)


def build_prompt(template: str, os_target: str, instruction: str) -> str | list[dict]:
    """A string for a text template, a list of chat messages for a chat template."""
    # str.replace and not str.format: templates contain shell braces like {}
    filled = template.replace("{os_target}", os_target).replace("{instruction}", instruction)
    if not _CHAT_ROLE.match(filled.lstrip()):
        return filled
    parts = _CHAT_ROLE.split(filled.lstrip())[1:]
    return [{"role": role, "content": text.strip()} for role, text in zip(parts[::2], parts[1::2])]


def call_llm(prompt: str | list[dict]) -> str:
    if isinstance(prompt, list):
        url, body, answer = OLLAMA_CHAT_URL, {"messages": prompt}, lambda j: j["message"]["content"]
    else:
        url, body, answer = OLLAMA_URL, {"prompt": prompt}, lambda j: j["response"]
    resp = requests.post(url, json={"model": MODEL, "stream": False, "options": MODEL_OPTIONS, **body}, timeout=120)
    resp.raise_for_status()
    return answer(resp.json()).strip()


@dataclass
class AgentResult:
    raw: str                 # exactly what the model returned
    command: str             # the command after light cleanup ("" when blocked / unsupported)
    model_verdict: str       # what the model itself said: SAFE / CONFIRM / BLOCKED / UNSUPPORTED
    final_verdict: str       # after the code guard
    reasons: list[str] = field(default_factory=list)


def _strip_fences(text: str) -> str:
    """Remove ``` fences and surrounding backticks. Nothing else is fixed."""
    text = text.strip()
    fence = re.fullmatch(r"```[\w-]*\s*\n?(.*?)\n?```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    if len(text) > 1 and text.startswith("`") and text.endswith("`") and "\n" not in text:
        text = text.strip("`").strip()
    return text


def parse(raw: str) -> AgentResult:
    text = _strip_fences(raw)

    if re.match(r"BLOCKED\b", text, re.IGNORECASE):
        reason = text.split(":", 1)[1].strip() if ":" in text else "blocked by the model"
        return AgentResult(raw, "", safety.BLOCKED, safety.BLOCKED, [f"model: {reason}"])
    if re.match(UNSUPPORTED, text, re.IGNORECASE):
        return AgentResult(raw, "", UNSUPPORTED, UNSUPPORTED, [])
    # "WARN:cmd", "WARN: cmd", "Warn cmd" - the model is not always exact
    warn = re.match(r"WARN\b\s*:?\s*", text, re.IGNORECASE)
    if warn:
        return AgentResult(raw, text[warn.end():].strip(), safety.CONFIRM, safety.CONFIRM, ["model: needs confirmation"])
    return AgentResult(raw, text, safety.SAFE, safety.SAFE, [])


def apply_guard(result: AgentResult) -> AgentResult:
    if result.final_verdict in (safety.BLOCKED, UNSUPPORTED):
        return result
    level, reasons = safety.classify(result.command)
    result.final_verdict = safety.stricter(result.final_verdict, level)
    result.reasons += reasons
    return result


def generate(instruction: str, os_target: str, prompt_version: str, prompts: dict[str, str] | None = None) -> AgentResult:
    prompts = prompts or load_prompts()
    raw = call_llm(build_prompt(prompts[prompt_version], os_target, instruction))
    return apply_guard(parse(raw))
