# web-vision — Claude Code Plugin

Give Claude eyes. Screenshot any URL, PDF, or HTML file and let Claude read it visually.

No MCP server, no API keys, no complex config — just `pixelrag-render` (a CLI that captures web pages as tiled images) + a skill that teaches Claude when and how to use it.

## Try it now

```bash
git clone <repo> && cd pixelrag
./plugin/setup.sh
claude --plugin-dir ./plugin "look at the Hacker News front page and summarize the top 5 stories"
```

That's it. Claude will screenshot the page, read the tiles, and tell you what it sees.

More examples:

```bash
# Check a deployment
claude --plugin-dir ./plugin "screenshot localhost:3000 and check if the login page looks correct"

# Read a paper
claude --plugin-dir ./plugin "visually read the first page of this paper: https://arxiv.org/pdf/2410.10594"

# Compare two pages
claude --plugin-dir ./plugin "screenshot both our staging and production homepages and spot the differences"
```

## What happens when you run it

Claude enters an interactive session and:

1. Recognizes it needs to see a web page
2. Runs `pixelrag-render <url> --output /tmp/web-vision` via Bash
3. Lists the output tile images
4. Reads each tile visually (top of page → bottom)
5. Responds based on what it saw

You'll see every step in real-time in the Claude Code UI.

## Quick Start

```bash
# First time: install pixelrag-render + Chromium
./setup.sh

# Start interactive session with plugin loaded
claude --plugin-dir .

# Or with an initial prompt
claude --plugin-dir . "what does the Hacker News front page look like right now?"
```

Once inside, you can also use the slash command:

```
/screenshot <url-or-file>
```

## What's inside

```
plugin/
├── .claude-plugin/plugin.json    — Plugin metadata
├── skills/web-vision/SKILL.md    — Teaches Claude to screenshot & read pages
├── commands/screenshot.md        — /screenshot slash command
├── setup.sh                      — One-time install (pixelrag-render + Chromium)
└── README.md
```

## How it works

1. Claude decides it needs to see a web page (or you say `/screenshot <url>`)
2. Claude runs `pixelrag-render <url> --output /tmp/web-vision` via Bash
3. `pixelrag-render` launches headless Chromium, captures the full page as tiled JPEGs
4. Claude reads the tile images and describes/acts on what it sees

No daemon, no server, no network calls beyond fetching the target page.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (for installing pixelrag-render)
- Chromium (auto-installed by `setup.sh`)

## Install

```bash
git clone <repo>
cd pixelrag
./plugin/setup.sh
claude --plugin-dir ./plugin
```

If `pixelrag-render` is published to PyPI (future):

```bash
uv tool install pixelrag-render
claude --plugin-dir ./plugin
```

## How is this different from Playwright MCP / browser-use?

| | web-vision | Playwright MCP | browser-use |
|---|---|---|---|
| Approach | Screenshot → vision | DOM interaction | Full browser automation |
| Context cost | ~0 tokens (Bash call) | ~14k tokens (tool schemas) | ~20k+ tokens |
| Can interact? | No (read-only) | Yes | Yes |
| Setup | One CLI tool | MCP server process | MCP server + browser |
| Best for | Reading/viewing pages | Testing/clicking | Complex web tasks |

web-vision is intentionally minimal: it's for **seeing**, not **interacting**. If you just need Claude to look at a page and understand its visual content, this is the lightest option.
