---
name: screenshot
description: Screenshot a URL or document and read it visually
allowed-tools: "Bash, Read"
---

1. Run: `pixelrag-render $ARGUMENTS --output /tmp/web-vision --tile-height 1568`
2. The output tile is at `/tmp/web-vision/<domain>.png.tiles/tile_0000.jpg` — read it directly with the Read tool. Do not ls.
3. If text is too small to read, crop with Pillow (always available — it's a pixelrag-render dependency):
   `python3 -c "from PIL import Image; Image.open('<tile>').crop((x1,y1,x2,y2)).save('/tmp/web-vision/crop.png')"`
4. Report what you see.
