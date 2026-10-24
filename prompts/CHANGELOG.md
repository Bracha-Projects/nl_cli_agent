# Prompt iterations

Same 30 test cases, same model (`llama3.2` 3B, temperature 0, seed 42) for every version.
One problem per iteration. Numbers are % of cases (from `results/results.xlsx`).

| Version | Problem it went after | What changed | correct | format | safety_model | safety_final | sandbox | overall |
|---|---|---|---|---|---|---|---|---|
| v1_basic | - (baseline) | one-paragraph prompt | 43.3 | 60.0 | 66.7 | 96.3 | 66.7 | 23.3 |
| v2_format | backticks, explanations, several options | rules: one command, no markdown, `UNSUPPORTED` | 36.7 | 93.3 | 66.7 | 96.3 | 66.7 | 36.7 |
| v3_safety | dangerous commands came out as normal output | `BLOCKED:` / `WARN:` protocol + pattern lists | 43.3 | 93.3 | 74.1 | 100 | 64.7 | 43.3 |
| v4_shell | wrong shell (`ipconfig` on Linux, `rm` on Windows, `ls -l` in PowerShell) | v3 + a "TARGET SHELL" block per OS | 30.0 | 83.3 | 64.8 | 72.2 | 55.6 | **20.0** ⬇ |
| v5_examples | rules don't work on a 3B model (v4) - **reverted to v3** and tried examples | v3 + 9 few-shot examples (none from the test set), 2 in Hebrew | 36.7 | 96.7 | 81.5 | 88.9 | 66.7 | 33.3 |
| v6_no_warn | `WARN:` on harmless commands (`WARN:ipconfig`) in v4 and v5 | v5 without the WARN job - the code guard decides "confirm" | 40.0 | 96.7 | 74.1 | 92.6 | 72.2 | 40.0 |
| v7_scope | poem / "fix my computer" / prompt injection still answered | v6 + SCOPE rules, `<instruction>` tags, 2 refusal examples | 26.7 | 93.3 | 70.4 | 85.2 | 63.2 | **26.7** ⬇ |
| v8_chat | the model copies example commands (`copy ...` everywhere in v7) | **same content as v6**, sent as a chat: rules = system, examples = past user/assistant turns | 63.3 | 93.3 | 81.5 | 100 | 81.2 | **60.0** ⬆ |
| v9_chat_scope | retry v7's scope idea without v7's text format | v8 + the SCOPE rules and the 2 refusal examples as chat turns | 70.0 | 100 | 74.1 | 92.6 | 78.6 | **70.0** ⬆ |

## Notes per version

**v1 → v2.** Format went 60 → 93. The rules did their job. Correctness did not improve
(43 → 37): format and correctness are separate problems.

**v2 → v3.** The model started to answer `BLOCKED:` / `WARN:`, but `rm -rf /` - which is
written *inside* the v3 block list - still came out as a plain command. A pattern list is
not a guarantee. This is why `safety.py` exists.

**v3 → v4 (regression).** The longer prompt made the model put `WARN:` in front of
almost everything (`WARN:ipconfig`), and block `grep`. The shell problem it targeted was
not fixed: `ipconfig getifaddr`, which v4 names as forbidden, still came out.
Naming the wrong answer seems to put it in the model's mind.

**v4 → v5.** Reverted to v3 and changed the method: show, don't tell. Format reached 97
and the model now blocked `shutdown` and `rm -rf /` by itself (safety_model 81.5). The
`WARN:` false alarms were still there.

**v5 → v6.** Removed one job from the model (deciding WARN) and gave it to code. The
false alarms disappeared and `ipconfig` passed again.

**v6 → v7 (regression).** The scope rules did not fix a single scope case. Worse, CMD
answers became `copy ...` in 6 of 7 cases, and Linux answers became `find ...`.
The examples were being continued as text.

**v7 → v8.** Nothing in the wording changed from v6. Only the structure: system message +
example chat turns + the real request as the last user message. Overall 40 → 60, 3 of the 4
Hebrew task examples pass. The biggest jump of the whole project came from structure,
not from wording.

**v8 → v9.** The v7 idea, now as chat turns: "fix my computer" → `UNSUPPORTED`, the
injection is refused (as `BLOCKED:explanation` - the right decision with the wrong label),
format and syntax 100. New regression: two harmless Hebrew requests are refused, one as
`BLOCKED:dd if=/dev/sda ...`.
