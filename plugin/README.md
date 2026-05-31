# pixelbrowse — Claude Code plugin

Give Claude eyes: screenshot any URL or document with `pixelshot` and read it visually.

## Setup

```bash
./setup.sh
```

## Use

After setup, start Claude Code with the plugin:

```bash
claude --plugin-dir .
```

Then ask: *"look at https://example.com and tell me what you see"* — Claude uses the **pixelbrowse** skill to screenshot the page and read the tiles.

Or use the slash command: `/screenshot <url>`.

The skill lives in `skills/pixelbrowse/SKILL.md`; the command in `commands/screenshot.md`.

No MCP server or backend — just `pixelshot` (Playwright/CDP) on your machine.
