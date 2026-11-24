"""Plan, apply and verify the Claude Code and Codex setup for a vault. Blocking: use asyncio.to_thread."""
from __future__ import annotations

import copy
import difflib
import json
import os
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

from src.errors import BrainSyncError
from src.fsutil import write_atomic

BEGIN, END = "<!-- brainsync:begin -->", "<!-- brainsync:end -->"


class SetupError(BrainSyncError):
    pass


@dataclass
class Op:
    label: str
    target: Path | None = None
    new: bytes | None = None
    link_to: Path | None = None
    cmd: list[str] | None = None
    manual: str | None = None
    before: bytes | None = None


def replace_block(text: str, body: str) -> str:
    block = f"{BEGIN}\n{body.strip()}\n{END}"
    if BEGIN in text and END in text:
        s = text.index(BEGIN)
        return text[:s] + block + text[text.index(END, s) + len(END):]
    lead = "" if not text or text.endswith("\n") else "\n"
    return text + lead + ("\n" if text else "") + block + "\n"


def _sub(v, subs: dict):
    if isinstance(v, str):
        for k, x in subs.items():
            v = v.replace(k, x)
        return v
    if isinstance(v, list):
        return [_sub(i, subs) for i in v]
    if isinstance(v, dict):
        return {k: _sub(x, subs) for k, x in v.items() if k != "_comment"}
    return v


def _merge(dst, src):
    if isinstance(dst, dict) and isinstance(src, dict):
        for k, v in src.items():
            dst[k] = _merge(dst[k], v) if k in dst else v
    elif isinstance(dst, list) and isinstance(src, list):
        dst.extend(x for x in src if x not in dst)
    return dst


def merge_settings(existing: dict, snippet: dict, subs: dict, extra_dirs: list[str]) -> dict:
    out = _merge(copy.deepcopy(existing), _sub(snippet, subs))
    dirs = out.setdefault("permissions", {}).setdefault("additionalDirectories", [])
    dirs.extend(d for d in extra_dirs if d not in dirs)
    return out


def insert_writable_roots(text: str, roots: list[str]) -> str | None:
    """Add roots to [sandbox_workspace_write].writable_roots; None means edit by hand."""
    want = [r.replace("\\", "/") for r in roots]
    lines = text.splitlines(keepends=True)
    hdr = next((i for i, l in enumerate(lines) if l.strip() == "[sandbox_workspace_write]"), None)
    arr = lambda xs: "writable_roots = [" + ", ".join(json.dumps(x) for x in xs) + "]\n"  # noqa: E731
    if hdr is None:
        lead = "" if not text or text.endswith("\n") else "\n"
        new = text + lead + ("\n" if text else "") + "[sandbox_workspace_write]\n" + arr(want)
    else:
        end = next((i for i in range(hdr + 1, len(lines)) if lines[i].lstrip().startswith("[")), len(lines))
        idx = next((i for i in range(hdr + 1, end) if lines[i].split("=")[0].strip() == "writable_roots"), None)
        if idx is None:
            lines.insert(hdr + 1, arr(want))
        else:
            if "[" not in lines[idx] or "]" not in lines[idx]:
                return None
            try:
                have = tomllib.loads(lines[idx].strip())["writable_roots"]
            except (tomllib.TOMLDecodeError, KeyError):
                return None
            missing = [r for r in want if r not in have]
            if not missing:
                return text
            lines[idx] = arr(have + missing)
        new = "".join(lines)
    try:
        tomllib.loads(new)
    except tomllib.TOMLDecodeError:
        return None
    return new


def build_plan(vault: Path, *, home: Path, projects_root: str, codex: bool, others: list[Path],
               py: str = "py", codex_home: Path | None = None, claude_on: bool = True) -> list[Op]:
    if not (claude_on or codex):
        raise SetupError("choose Claude Code, Codex or both")
    setup = vault / "_setup"
    if not setup.is_dir():
        raise SetupError("vault has no _setup folder")
    claude = home / ".claude"
    hooks = claude / "hooks"
    subs = {"<VAULT_PATH>": vault.as_posix(), "<PROJECTS_ROOT>": projects_root.replace("\\", "/"),
            "<PY>": py, "<HOOKS_DIR>": hooks.as_posix()}
    ops: list[Op] = []

    def put(label: str, target: Path, data: bytes) -> None:
        ops.append(Op(label, target, data, before=target.read_bytes() if target.is_file() else None))

    def block(label: str, target: Path, template: Path) -> None:
        old = target.read_text("utf-8") if target.is_file() else ""
        put(label, target, replace_block(old, _sub(template.read_text("utf-8"), subs)).encode("utf-8"))

    if claude_on and (setup / "hooks").is_dir():
        for f in sorted((setup / "hooks").glob("*.py")):
            put(f"hook {f.name}", hooks / f.name, f.read_bytes())
    if claude_on:
        put("vault path", hooks / "vault_path.txt", (vault.as_posix() + "\n").encode())
    skills = sorted(p for p in (setup / "skills").iterdir() if p.is_dir()) if (setup / "skills").is_dir() else []
    for d in skills:
        for f in sorted(d.rglob("*")):
            if f.is_file():
                rel = f.relative_to(d)
                put(f"skill {d.name}/{rel.as_posix()}", claude / "skills" / d.name / rel, f.read_bytes())
    sp = claude / "settings.json"
    try:
        existing = json.loads(sp.read_text("utf-8")) if sp.is_file() else {}
    except ValueError:
        existing = None
    if not claude_on:
        pass
    elif not isinstance(existing, dict):
        ops.append(Op("settings.json", sp, manual="settings.json is not valid JSON. Fix it by hand, then plan again."))
    else:
        snippet = json.loads((setup / "settings.snippet.json").read_text("utf-8"))
        merged = merge_settings(existing, snippet, subs, [o.as_posix() for o in others])
        put("settings.json", sp, (json.dumps(merged, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    if claude_on:
        block("CLAUDE.md block", claude / "CLAUDE.md", setup / "user-CLAUDE.md.template")
    if codex:
        ch = codex_home or Path(os.environ.get("CODEX_HOME") or home / ".codex")
        block("Codex AGENTS.md block", ch / "AGENTS.md", setup / "user-AGENTS.md.template")
        for d in skills:
            ops.append(Op(f"Codex skill link {d.name}", ch / "skills" / d.name, link_to=claude / "skills" / d.name))
        cfg = ch / "config.toml"
        roots = [vault.as_posix(), *[o.as_posix() for o in others]]
        new = insert_writable_roots(cfg.read_text("utf-8") if cfg.is_file() else "", roots)
        if new is None:
            ops.append(Op("Codex config.toml", cfg, manual="Add these to [sandbox_workspace_write] writable_roots by hand: "
                          + ", ".join(roots)))
        else:
            put("Codex config.toml", cfg, new.encode("utf-8"))
    if not (vault / ".git").exists():
        ops.append(Op("git init", cmd=["git", "-C", str(vault), "init", "-b", "main"]))
    return ops


def render_diff(op: Op) -> str:
    if op.manual:
        return op.manual
    if op.cmd:
        return "run: " + " ".join(op.cmd)
    if op.link_to:
        return f"link {op.target} -> {op.link_to}"
    if op.before == op.new:
        return "no change"
    old = (op.before or b"").decode("utf-8", "replace").splitlines()
    new = (op.new or b"").decode("utf-8", "replace").splitlines()
    head = "new file\n" if op.before is None else ""
    return head + "\n".join(difflib.unified_diff(old, new, "before", "after", lineterm=""))


def apply_plan(ops: list[Op], selected: set[int], backup_dir: Path) -> list[dict]:
    results = []
    for i, op in enumerate(ops):
        if i not in selected:
            continue
        r = {"id": i, "label": op.label, "status": "ok", "detail": ""}
        try:
            if op.manual:
                r.update(status="manual", detail=op.manual)
            elif op.cmd:
                p = subprocess.run(op.cmd, capture_output=True, text=True, timeout=30)
                if p.returncode:
                    r.update(status="error", detail=(p.stderr or p.stdout).strip()[:200])
            elif op.link_to:
                if op.target.is_symlink() or op.target.exists():
                    same = op.target.resolve() == op.link_to.resolve()
                    r.update(status="unchanged" if same else "error",
                             detail="" if same else "something else is already there; remove it by hand")
                else:
                    op.target.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        os.symlink(op.link_to, op.target, target_is_directory=True)
                    except OSError:
                        r.update(status="error", detail="symlink failed; turn on Windows Developer Mode")
            elif op.before == op.new:
                r["status"] = "unchanged"
            else:
                if op.target.is_file():
                    backup_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(op.target, backup_dir / f"{i:03d}-{op.target.name}")
                write_atomic(op.target, op.new)
        except (OSError, subprocess.SubprocessError) as e:
            r.update(status="error", detail=type(e).__name__)
        results.append(r)
    return results


def verify(vault: Path, home: Path, py: str = "py") -> list[dict]:
    if not shutil.which(py):
        py = sys.executable
    hooks = home / ".claude" / "hooks"
    env = {**os.environ, "BRAIN_VAULT": str(vault)}
    checks = [
        ("validate_vault --all", [py, str(hooks / "validate_vault.py"), "--all"], lambda p: "vault OK" in p.stdout),
        ("ensure_daily", [py, str(hooks / "ensure_daily.py")], lambda p: p.returncode == 0),
        ("autocommit --dry-run", [py, str(hooks / "autocommit_vault.py"), "--dry-run"], lambda p: p.returncode == 0),
        ("git status clean", ["git", "-C", str(vault), "status", "--porcelain"],
         lambda p: p.returncode == 0 and not p.stdout.strip()),
    ]
    rows = []
    for name, cmd, ok in checks:
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=60, env=env)
            rows.append({"name": name, "ok": bool(ok(p)), "detail": (p.stdout or p.stderr).strip()[:200]})
        except (OSError, subprocess.SubprocessError) as e:
            rows.append({"name": name, "ok": False, "detail": type(e).__name__})
    skills = vault / "_setup" / "skills"
    names = [d.name for d in skills.iterdir() if d.is_dir()] if skills.is_dir() else []
    missing = [n for n in names if not (home / ".claude" / "skills" / n).is_dir()]
    rows.append({"name": "skills installed", "ok": not missing, "detail": ", ".join(missing)})
    return rows
