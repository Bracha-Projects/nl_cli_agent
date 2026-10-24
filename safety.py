"""Deterministic safety guard.

The prompt asks the model to flag dangerous commands, but a 3B model does not
always listen. This guard checks the final command in code, so the decision
does not depend on the model alone.

Levels:
  SAFE     - can run as is
  CONFIRM  - risky, the user must confirm before it runs
  BLOCKED  - forbidden, never runs
"""

import re

SAFE, CONFIRM, BLOCKED = "SAFE", "CONFIRM", "BLOCKED"
_ORDER = {SAFE: 0, CONFIRM: 1, BLOCKED: 2}

# Command names (first word of a segment) that are forbidden outright.
BLOCKED_COMMANDS = {
    # deleting files / folders
    "rm": "deletes files",
    "del": "deletes files",
    "erase": "deletes files",
    "rd": "deletes folders",
    "rmdir": "deletes folders",
    "remove-item": "deletes files",
    "ri": "deletes files",
    "unlink": "deletes files",
    "shred": "destroys files",
    # power
    "shutdown": "shuts the machine down",
    "reboot": "restarts the machine",
    "halt": "stops the machine",
    "poweroff": "turns the machine off",
    "stop-computer": "shuts the machine down",
    "restart-computer": "restarts the machine",
    # disks
    "format": "formats a drive",
    "diskpart": "edits disk partitions",
    "fdisk": "edits disk partitions",
    "parted": "edits disk partitions",
    "wipefs": "wipes a disk",
    "format-volume": "formats a drive",
    "clear-disk": "wipes a disk",
    "bcdedit": "changes boot settings",
}

# Patterns checked on the whole command line.
BLOCKED_PATTERNS = [
    (r"\bmkfs(\.\w+)?\b", "formats a drive"),
    (r"\bdiskutil\s+(erase\w*|zero\w*|secureerase|partitiondisk|reformat)\b", "erases a disk"),
    (r"\bdd\b.*\bof=/dev/", "writes raw data to a disk"),
    (r">\s*/dev/(sd|nvme|hd|disk)", "writes raw data to a disk"),
    (r":\(\)\s*\{.*\};\s*:", "fork bomb"),
    (r"\b(curl|wget|iwr|invoke-webrequest)\b.*\|\s*(ba|z)?sh\b", "runs a script from the internet"),
    (r"\b(iex|invoke-expression)\b", "runs code from a string"),
    (r"\bsystemctl\s+(poweroff|reboot|halt)\b", "shuts the machine down"),
    (r"\binit\s+[06]\b", "shuts the machine down"),
    (r"\breg\s+delete\b", "deletes registry keys"),
    (r"\bvssadmin\s+delete\b", "deletes backups"),
    (r"\bcipher\s+/w\b", "wipes free disk space"),
    (r"\bchmod\s+(-R\s+)?[0-7]*777\s+/(\s|$)", "opens the whole file system"),
    (r"\bchown\s+-R\s+\S+\s+/(\s|$)", "changes owner of the whole file system"),
    (r"\bfind\b.*\s-delete\b", "deletes files"),
    (r"\bfind\b.*-exec\s+rm\b", "deletes files"),
    (r"\bxargs\s+(-\S+\s+)*rm\b", "deletes files"),
    (r"\bgit\s+clean\s+-\w*f", "deletes untracked files"),
]

# Command names that need the user to confirm first.
CONFIRM_COMMANDS = {
    "sudo": "runs as administrator",
    "su": "switches user",
    "runas": "runs as another user",
    "kill": "stops a process",
    "pkill": "stops processes",
    "killall": "stops processes",
    "taskkill": "stops a process",
    "stop-process": "stops a process",
    "chmod": "changes permissions",
    "chown": "changes owner",
    "icacls": "changes permissions",
    "attrib": "changes file attributes",
    "takeown": "takes ownership of files",
    "mv": "moves or renames files",
    "move": "moves files",
    "move-item": "moves files",
    "ren": "renames files",
    "rename": "renames files",
    "rename-item": "renames files",
    "setx": "changes environment variables",
    "crontab": "changes scheduled jobs",
    "schtasks": "changes scheduled tasks",
    "iptables": "changes the firewall",
    "ufw": "changes the firewall",
    "dd": "low level copy",
    "truncate": "empties files",
}

CONFIRM_PATTERNS = [
    (r"\bnet\s+(stop|start|user|localgroup)\b", "changes services or users"),
    (r"\bsc\s+(stop|start|delete|config)\b", "changes services"),
    (r"\bsystemctl\s+(stop|start|restart|disable|enable|mask)\b", "changes services"),
    (r"\bservice\s+\S+\s+(stop|start|restart)\b", "changes services"),
    (r"\b(stop|start|restart|set)-service\b", "changes services"),
    (r"\b(apt|apt-get|yum|dnf|brew|choco|winget|pip|npm|snap)\s+(install|remove|uninstall|purge|upgrade)\b", "installs or removes software"),
    (r"\breg\s+add\b", "changes the registry"),
    (r"\bnetsh\b.*\b(set|add|delete)\b", "changes network settings"),
    (r"\bgit\s+(push\s+.*--force|push\s+-f|reset\s+--hard)\b", "rewrites git history"),
]

_SEGMENT_SPLIT = re.compile(r"\|\||&&|[;|&\n]")


# Words that run the next word as a command: "sudo rm", "xargs kill", "nohup ..."
WRAPPERS = {"sudo", "doas", "xargs", "nohup", "nice", "time", "env", "command", "exec", "timeout", "start", "call"}


def _normalize(word: str) -> str:
    word = word.lower().strip("(\"'$`")
    # "C:\Windows\System32\shutdown.exe" -> "shutdown"
    word = re.split(r"[\\/]", word)[-1]
    return re.sub(r"\.(exe|cmd|bat|com)$", "", word)


def _command_words(segment: str) -> list[str]:
    """The command word of a segment, plus the command behind any wrapper.

    "sudo xargs -r rm -f" -> ["sudo", "xargs", "rm"]
    """
    words = [_normalize(w) for w in segment.strip().split()]
    found = []
    i = 0
    while i < len(words):
        found.append(words[i])
        if words[i] not in WRAPPERS:
            break
        i += 1
        # skip the wrapper's own options and arguments like "timeout 5" or "env A=1"
        while i < len(words) and (words[i].startswith("-") or "=" in words[i] or words[i].isdigit()):
            i += 1
    return found


def classify(command: str) -> tuple[str, list[str]]:
    """Return (level, reasons) for a command line."""
    if not command or not command.strip():
        return SAFE, []

    level, reasons = SAFE, []

    def bump(new_level: str, reason: str):
        nonlocal level
        if reason not in reasons:
            reasons.append(reason)
        if _ORDER[new_level] > _ORDER[level]:
            level = new_level

    for segment in _SEGMENT_SPLIT.split(command):
        for word in _command_words(segment):
            if word in BLOCKED_COMMANDS:
                bump(BLOCKED, f"{word}: {BLOCKED_COMMANDS[word]}")
            elif word in CONFIRM_COMMANDS:
                bump(CONFIRM, f"{word}: {CONFIRM_COMMANDS[word]}")

    for pattern, reason in BLOCKED_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            bump(BLOCKED, reason)
    for pattern, reason in CONFIRM_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            bump(CONFIRM, reason)

    return level, reasons


def stricter(a: str, b: str) -> str:
    return a if _ORDER[a] >= _ORDER[b] else b
