import gradio as gr
import requests

import agent
import safety
import sandbox

PROMPTS = agent.load_prompts()
DEFAULT_VERSION = list(PROMPTS)[-1]  # the newest iteration

STATUS = {
    safety.SAFE: "✅ Ready",
    safety.CONFIRM: "⚠️ Risky - confirm before running",
    safety.BLOCKED: "🚫 Blocked - will never run",
    agent.UNSUPPORTED: "❓ Unsupported",
}


# ─── Core agent ───────────────────────────────────────────────────────────────

def run_agent(instruction, os_target, prompt_version):
    """Returns: command, status, safety note, raw model output, verdict (kept in state)."""
    if not instruction.strip():
        return "", "—", "", "", ""
    try:
        result = agent.generate(instruction, os_target, prompt_version, PROMPTS)
    except requests.exceptions.ConnectionError:
        return "", "❌ Ollama not running", "Start ollama with: ollama serve", "", ""
    except Exception as e:
        return "", f"❌ {e}", "", "", ""
    return result.command, STATUS[result.final_verdict], "; ".join(result.reasons), result.raw, result.final_verdict


def run_in_sandbox(command, os_target, verdict, confirmed):
    if not command.strip() or verdict == agent.UNSUPPORTED:
        return "Nothing to run."
    if os_target != agent.OS_TARGETS[0]:
        return "The sandbox is a Linux container, so it only runs Linux / macOS commands."
    if verdict == safety.BLOCKED:
        return "🚫 This command is forbidden and will not run, not even in the sandbox."
    # check the text in the box again: the user may have edited it
    level, reasons = safety.classify(command)
    if level == safety.BLOCKED:
        return f"🚫 Forbidden: {'; '.join(reasons)}"
    if safety.CONFIRM in (level, verdict) and not confirmed:
        return "⚠️ This command is risky. Tick 'I understand the risk' and press Run again."
    result = sandbox.run(command)
    if result.exit_code is None:
        return result.output
    return f"exit code: {result.exit_code}\n\n{result.output}"


# ─── Gradio UI ────────────────────────────────────────────────────────────────

with gr.Blocks(title="NL → CLI Agent") as demo:
    gr.Markdown("# 🖥️ Natural Language → CLI Agent")
    gr.Markdown("Powered by **ollama** (local model, no API key needed). "
                "Commands run only inside a throw-away Docker sandbox, never on this computer.")

    verdict_state = gr.State("")

    with gr.Row():
        os_radio = gr.Radio(choices=agent.OS_TARGETS, value=agent.OS_TARGETS[0], label="Target OS")
        prompt_dd = gr.Dropdown(choices=list(PROMPTS), value=DEFAULT_VERSION, label="Prompt iteration")

    instruction_box = gr.Textbox(
        label="Instruction (natural language, any language)",
        placeholder="e.g. show all running processes sorted by memory usage",
        lines=2,
    )

    run_btn = gr.Button("Convert →", variant="primary")

    with gr.Row():
        cmd_out = gr.Textbox(label="CLI Command", lines=2, interactive=True)
        status_out = gr.Textbox(label="Status", lines=1, interactive=False)

    note_out = gr.Textbox(label="Safety note", lines=1, interactive=False)
    with gr.Accordion("Raw model output", open=False):
        raw_out = gr.Textbox(show_label=False, lines=3, interactive=False)

    with gr.Row():
        confirm_box = gr.Checkbox(label="I understand the risk", value=False)
        sandbox_btn = gr.Button("▶ Run in sandbox")
    sandbox_out = gr.Textbox(label="Sandbox output", lines=6, interactive=False)

    gr.Examples(
        examples=[
            ["what is my IP address", "Linux / macOS"],
            ["מה כתובת ה-IP של המחשב שלי", "Windows (CMD)"],
            ["count the lines in report.txt", "Linux / macOS"],
            ["kill the process that is listening on port 8080", "Linux / macOS"],
            ["shut down the computer immediately", "Linux / macOS"],
            ["find all .log files modified in the last 7 days", "Linux / macOS"],
        ],
        inputs=[instruction_box, os_radio],
    )

    run_btn.click(
        fn=run_agent,
        inputs=[instruction_box, os_radio, prompt_dd],
        outputs=[cmd_out, status_out, note_out, raw_out, verdict_state],
    ).then(lambda: (False, ""), outputs=[confirm_box, sandbox_out])

    sandbox_btn.click(
        fn=run_in_sandbox,
        inputs=[cmd_out, os_radio, verdict_state, confirm_box],
        outputs=[sandbox_out],
    )

if __name__ == "__main__":
    demo.launch()
