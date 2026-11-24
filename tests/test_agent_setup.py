import json
import tomllib

from src.agent_setup import BEGIN, apply_plan, build_plan, insert_writable_roots, merge_settings, replace_block
from tests.helpers import make_vault

SNIP = {"_comment": "x",
        "permissions": {"additionalDirectories": ["<VAULT_PATH>"], "deny": ["Read(**/.env)"]},
        "hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": '<PY> "<HOOKS_DIR>/ensure_daily.py"'}]}]}}


def test_merge_settings_idempotent():
    subs = {"<VAULT_PATH>": "D:/v", "<PY>": "py", "<HOOKS_DIR>": "C:/h"}
    existing = {"model": "x", "permissions": {"deny": ["Bash(rm -rf:*)"]},
                "hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "other"}]}]}}
    once = merge_settings(existing, SNIP, subs, ["E:/other"])
    twice = merge_settings(once, SNIP, subs, ["E:/other"])
    assert once == twice and "_comment" not in once and once["model"] == "x"
    assert once["permissions"]["additionalDirectories"] == ["D:/v", "E:/other"]
    assert once["permissions"]["deny"] == ["Bash(rm -rf:*)", "Read(**/.env)"]
    assert len(once["hooks"]["SessionStart"]) == 2
    assert once["hooks"]["SessionStart"][1]["hooks"][0]["command"] == 'py "C:/h/ensure_daily.py"'


def test_block_idempotent():
    a = replace_block("keep\n", "body1")
    b = replace_block(a, "body2")
    assert replace_block(b, "body2") == b and "body1" not in b and b.startswith("keep\n") and b.count(BEGIN) == 1


def test_toml_roots():
    roots = lambda s: tomllib.loads(s)["sandbox_workspace_write"]["writable_roots"]  # noqa: E731
    assert roots(insert_writable_roots("", ["D:/Brain"])) == ["D:/Brain"]
    r = insert_writable_roots("[sandbox_workspace_write]\nnetwork_access = true\n", ["D:/Brain"])
    assert roots(r) == ["D:/Brain"] and tomllib.loads(r)["sandbox_workspace_write"]["network_access"] is True
    r = insert_writable_roots('[sandbox_workspace_write]\nwritable_roots = ["C:/a"]\n', ["D:/Brain"])
    assert roots(r) == ["C:/a", "D:/Brain"] and insert_writable_roots(r, ["D:/Brain"]) == r
    assert insert_writable_roots('[sandbox_workspace_write]\nwritable_roots = [\n "C:/a",\n]\n', ["D:/Brain"]) is None


def test_plan_apply_twice(tmp_path):
    v = make_vault(tmp_path / "v", {
        "_setup/hooks/validate_vault.py": "print(1)", "_setup/skills/s1/SKILL.md": "skill",
        "_setup/settings.snippet.json": json.dumps(SNIP),
        "_setup/user-CLAUDE.md.template": "vault <VAULT_PATH>", "_setup/user-AGENTS.md.template": "a <VAULT_PATH>"})
    home = tmp_path / "home"

    def run(n):
        ops = build_plan(v, home=home, projects_root="D:/p", codex=False, others=[], py="py")
        assert any(o.cmd for o in ops)  # git init planned: vault has no .git
        return apply_plan(ops, {i for i, o in enumerate(ops) if o.cmd is None}, tmp_path / f"bk{n}")

    first, second = run(1), run(2)
    assert all(r["status"] in ("ok", "unchanged") for r in first)
    assert all(r["status"] == "unchanged" for r in second)
    assert (home / ".claude/skills/s1/SKILL.md").read_text() == "skill"
    assert (home / ".claude/hooks/vault_path.txt").read_text().strip() == v.as_posix()
    assert "vault " + v.as_posix() in (home / ".claude/CLAUDE.md").read_text()


def test_codex_only_skips_claude_files(tmp_path):
    import pytest
    v = make_vault(tmp_path / "v", {
        "_setup/hooks/h.py": "1", "_setup/skills/s1/SKILL.md": "s", "_setup/settings.snippet.json": json.dumps(SNIP),
        "_setup/user-CLAUDE.md.template": "c", "_setup/user-AGENTS.md.template": "a"})
    ops = build_plan(v, home=tmp_path / "h", projects_root="D:/p", codex=True, others=[], claude_on=False)
    labels = [o.label for o in ops]
    assert not any(x.startswith(("hook", "settings", "CLAUDE", "vault path")) for x in labels)
    assert "Codex AGENTS.md block" in labels and "skill s1/SKILL.md" in labels
    with pytest.raises(Exception):
        build_plan(v, home=tmp_path / "h", projects_root="D:/p", codex=False, others=[], claude_on=False)
