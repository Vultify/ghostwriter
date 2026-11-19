# Plan: speech model tiers (Phantom, Spirit, Wisp)

Planned 2026-11-18, not started. Most of the building and testing happens on my Windows PC, since it needs real graphics cards. Ghostwriter has no outside users yet, so there's nothing to migrate and no old setup to protect.

## Goal

Settings > Speech model stops asking people to pick an engine (the faster-whisper and whisper.cpp choice, plus the Model, Runs on, and Size list). Instead it offers three tiers named by how strong the PC is. Ghostwriter picks the right one on its own, and most people never change it.

## Decisions

- **One engine: whisper.cpp everywhere**, on Windows and Linux, NVIDIA cards included. It matched faster-whisper's accuracy and speed on my RTX 4090 (0.06 to 0.24 s), and I've dictated with it daily.
- **faster-whisper goes away completely**, with no hidden fallback: `transcriber.py`, the engine switch, `requirements-nvidia.txt` and its lock file, and the NVIDIA step in `install.bat`. New installs stop downloading about 1.3 GB of NVIDIA-only files. My own copy gets switched over by hand.
- **Three tiers**, all from the `ggerganov/whisper.cpp` repo and pinned in `models.REVISIONS` like the models today:

  | Tier | For | Model | Size |
  |---|---|---|---|
  | **Phantom** | High-end PCs | `ggml-large-v3-turbo.bin` (full size) | 1.6 GB |
  | **Spirit** | Laptops and mid-range PCs | `ggml-large-v3-turbo-q8_0.bin` (lightly compressed) | 874 MB |
  | **Wisp** | Older or low-power PCs | a small Whisper model, picked by testing (`small` or `base`, and their `.en` versions) | about 60 to 190 MB |

- **Spirit uses q8_0 instead of today's q5_0.** q8 stays much closer to the full model's accuracy. q5 was picked so weak PCs could run the large model, and Wisp covers those PCs now. q5_0 is no longer downloaded.
- **No processor-only mode.** A PC that can't run Wisp on its graphics gets a clear message that it's too weak for Ghostwriter. My Omarchy laptop (UHD 600) is in that group, and it isn't a target.
- **Settings save the tier, not the model:** `"tier": "auto" | "phantom" | "spirit" | "wisp"`. Swapping a tier's model later updates everyone on that tier. The `engine` setting is removed; an old settings file just loads with defaults for what it doesn't recognize.

## Picking a tier on first run

The first dictation should work within a minute, so a new PC starts small and moves up instead of downloading a big model it might not keep.

1. **NVIDIA card:** straight to Phantom, with no speed test.
2. **Any other PC:** download Wisp, and dictation works as soon as it loads.
3. **Speed test:** time Wisp on a short bundled clip, warmed up, as a share of the clip's length (a 2 second clip and a 30 second ramble take very different times). If Wisp is fast enough that Spirit would still feel quick, download Spirit in the background and switch over live. The existing engine switching already keeps the old model dictating until the new one is ready. A very fast card without NVIDIA (a high-end AMD) can step up to Phantom the same way.
4. **Failures:** if a run fails (the graphics chip resets, or the server errors), stay on or drop to the tier below. Never retry the same tier. If Wisp itself fails, show the too-weak message.
5. **Thresholds:** set from measurements, with the reasoning in a comment. The target is that a 10 second dictation types out in about a second.

The welcome screen says what it picked, for example "Picked Spirit for this PC."

## Check first, before building

- **q8_0 on built-in graphics.** The Intel UHD 770 in my desktop already took about 4 s with q5_0, and q8 is bigger. Run `scripts/compare_engines.py` with q8_0 there. If it's too slow for the laptops Spirit is meant for, rethink Spirit (keep q5_0, or move the split) before building anything.
- **Wisp's model.** Try `small`, `base`, and their `.en` versions on built-in graphics, and pick the best balance of speed and accuracy.
- **Accuracy against what I actually said.** `compare_engines.py` compares engines with faster-whisper, which shows agreement, not accuracy. Hand-check the transcripts of a few of my saved recordings (in `recordings\`) and measure every tier against those.

## Settings page

- Show the three tiers as choices, with a one-line description under each one that's visible without hovering. The names alone don't say which is stronger.
  - **Phantom:** For high-end PCs. Best accuracy.
  - **Spirit:** For laptops and mid-range PCs. Almost as accurate, lighter and faster.
  - **Wisp:** For older or low-power PCs. Fastest, a bit less accurate.
- Mark the tier Ghostwriter picked as **Recommended**.
- An **ⓘ** beside the choices (it opens on hover, tap, and keyboard focus) shows each tier's model, that it runs on whisper.cpp, and its size, plus "Running on: [graphics card]".
- Live switching and download progress keep working, worded by tier ("Downloading Spirit... 0.3 of 0.9 GB", "Switching to Wisp...").
- Remove the "faster-whisper is built for NVIDIA cards" hint and the Model, Runs on, and Size list.

## Testing

- My RTX 4090 desktop picks Phantom. A laptop or built-in graphics picks Spirit or Wisp, depending on the speed test. My Omarchy laptop gets the too-weak message.
- If a friend has an older NVIDIA card (a laptop GPU or GTX 10 series), dictate on it once, since faster-whisper won't be there to fall back on.
- Tests for picking a tier, the speed test's choice, dropping a tier after a failure, and old settings files loading cleanly.

## Docs

README (install sizes, the Settings section, the engine paragraph), CHANGELOG, and ROADMAP.
