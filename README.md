# TwinSync Spot

**Does this match YOUR definition?**

A Home Assistant Add-on that compares camera snapshots to *your own description* of how a space should look.

## The Idea

You define what "ready" means for each spot:

```
This is my kitchen. Ready state means:
- Counters clear and wiped
- No dishes in sink
- No food left out
```

TwinSync checks and reports:

```
📍 Kitchen - Needs Attention

To sort:
• Coffee mug on counter 🔄 (4th time this week!)
• Dishes in sink

Looking good:
• Stove is clear ✓
• No food out ✓

---
*That mug keeps coming back...*
🔥 Streak: 0 days (best: 5)
```

## Features

- **Your Definition** - You write what "ready" means in plain English
- **Memory System** - Remembers patterns over time ("coffee mug appears 80% of mornings")
- **6 Voices** - Choose how updates sound (Direct, Supportive, Analytical, Minimal, Gentle Nudge, Custom)
- **Streaks** - Track consecutive days sorted
- **Beautiful UI** - Proper web interface, not janky Lovelace cards

## Installation

### Home Assistant Add-on

1. Add this repository to your HA Add-on store:
   ```
   https://github.com/kozzzzzzy/twin-sync-addon
   ```

2. Install "TwinSync Spot"

3. Configure your Gemini API key in the add-on settings
   - Get one free at: https://aistudio.google.com/app/apikey

4. Start the add-on

5. Open from sidebar → TwinSync Spot

### Standalone Docker

```bash
docker run -p 8099:8099 \
  -e GEMINI_API_KEY=your_key \
  -v twinsync_data:/data \
  ghcr.io/kozzzzzzy/twin-sync-spot
```

Then open http://localhost:8099

## Requirements

- **Home Assistant 2024.6.0+** (for add-on mode)
- **Camera entity** for each spot
- **Gemini API key** (free tier is plenty)

## API Cost

Gemini free tier is generous:
- 15 requests/minute
- 1500 requests/day
- Typical usage: 2-4 checks × 3 spots = 6-12/day

## License

MIT - do whatever you want with it.

---

Made with 🎯 for people who know what "clean" means to them.
