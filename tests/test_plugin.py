"""Checks for the plugin marketplace files, against the rules in the Claude Code and Codex docs.

Neither `claude plugin validate` nor Codex can run in CI without an account, so these tests
encode the documented requirements: required fields, relative sources that stay inside the
marketplace root, matching names, and skills discovered from the plugin's skills/ folder.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from support import PLUGIN, REPO, SKILL

CLAUDE_MARKETPLACE = REPO / ".claude-plugin" / "marketplace.json"
CODEX_MARKETPLACE = REPO / ".agents" / "plugins" / "marketplace.json"
CLAUDE_MANIFEST = PLUGIN / ".claude-plugin" / "plugin.json"
CODEX_MANIFEST = PLUGIN / "plugin.json"
KEBAB = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve(source: str) -> Path:
    """A relative marketplace source, resolved from the marketplace root (the repo)."""
    assert source.startswith("./") and ".." not in Path(source).parts, source
    return (REPO / source).resolve()


class ClaudeMarketplaceTests(unittest.TestCase):
    def test_marketplace(self):
        data = load(CLAUDE_MARKETPLACE)
        self.assertRegex(data["name"], KEBAB)
        self.assertTrue(data["owner"]["name"])
        self.assertEqual(len(data["plugins"]), 1)
        entry = data["plugins"][0]
        self.assertEqual(resolve(entry["source"]), PLUGIN.resolve())
        self.assertTrue(entry["description"])

    def test_manifest(self):
        manifest = load(CLAUDE_MANIFEST)
        entry = load(CLAUDE_MARKETPLACE)["plugins"][0]
        self.assertEqual(manifest["name"], entry["name"])  # entry and manifest names must match
        self.assertRegex(manifest["name"], KEBAB)
        self.assertFalse(re.match(r"^(claude|anthropic|cc-plugin)-", manifest["name"]))
        for field in ("version", "description", "author", "license"):
            self.assertIn(field, manifest)
        # Everything except the manifest lives at the plugin root, not in .claude-plugin/.
        self.assertEqual(sorted(p.name for p in CLAUDE_MANIFEST.parent.iterdir()), ["plugin.json"])


class CodexMarketplaceTests(unittest.TestCase):
    def test_marketplace(self):
        data = load(CODEX_MARKETPLACE)
        self.assertRegex(data["name"], KEBAB)
        self.assertEqual(data["name"], load(CLAUDE_MARKETPLACE)["name"])
        self.assertEqual(len(data["plugins"]), 1)
        entry = data["plugins"][0]
        for field in ("name", "source", "policy", "category"):
            self.assertIn(field, entry)
        self.assertEqual(entry["source"]["source"], "local")
        self.assertEqual(resolve(entry["source"]["path"]), PLUGIN.resolve())
        self.assertEqual(set(entry["policy"]), {"installation", "authentication"})

    def test_manifest(self):
        manifest = load(CODEX_MANIFEST)
        self.assertEqual(manifest["name"], load(CODEX_MARKETPLACE)["plugins"][0]["name"])
        for field in ("name", "version", "description"):
            self.assertTrue(manifest[field])
        interface = manifest["extensions"]["com.openai"]["interface"]
        self.assertTrue(interface["displayName"])


class SharedPluginTests(unittest.TestCase):
    def test_manifests_agree(self):
        claude, codex = load(CLAUDE_MANIFEST), load(CODEX_MANIFEST)
        for field in ("name", "version", "description"):
            self.assertEqual(claude[field], codex[field], field)

    def test_version_tracks_pattern_version(self):
        version = (SKILL / "VERSION").read_text(encoding="utf-8").strip()
        for path in (CLAUDE_MANIFEST, CODEX_MANIFEST):
            self.assertEqual(load(path)["version"].split(".")[0], version, path)

    def test_skill_is_discovered_from_skills_folder(self):
        skills = sorted(p.parent.name for p in (PLUGIN / "skills").glob("*/SKILL.md"))
        self.assertEqual(skills, ["task-queue"])

    def test_plugin_has_no_hooks_or_context_files(self):
        # Hooks are per-project (install.py); plugin-level hooks would fire in every project.
        self.assertFalse((PLUGIN / "hooks").exists())
        self.assertFalse((PLUGIN / "CLAUDE.md").exists())


if __name__ == "__main__":
    unittest.main()
