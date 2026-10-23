# Project music candidate pool

`catalog.json` is the source of truth for imported audio identities, provenance,
attribution, technical measurements and candidate windows. `selection.json`
records the curated scope and inferred dramatic uses, not an automatic rating.

## First batch: discovery tags, not audition verdicts

| Work | Candidate dramatic use | Texture |
|---|---|---|
| Undertow (existing source) | Restrained conflict / revelation | Piano and strings |
| Signal to Noise (+ no-piano-melody mix) | Investigation / doubt | Cello, low strings and synth |
| The Old Ones | Unresolved danger / horror | Abstract strings and synth |
| Machina | Technology / surveillance | Glitchy electronic ambience |
| Snowfall | Memory / regret / loss | Layered piano and strings |
| Chasing Daylight | Care / reconciliation / recovery | Contemplative piano and strings |
| Felicity | Light romance / daily life | Folk-pop, mandolin, violin and drums |
| Pathfinder | Heroic reversal / victory | Brass-led adventure orchestra |
| Juggernaut | Menace / action escalation | Driving strings, brass and percussion |

## Use in an episode

1. Read the scene and mark the intended music entrance, exit and emotional job.
2. Filter catalog moods, instruments and use cases; consider the caution field.
3. Audition a few passages against the actual dialogue/picture. RMS windows are
   search starting points only: they do not detect musical phrases, beats,
   harmonic compatibility, emotion or dialogue masking.
4. Choose phrase-aware source in/out points and record asset ID/hash, timing,
   gain, fades, ducking and reason in the episode plan. Preserve silence where
   performance should lead. Do not reuse a catalog window blindly.
5. Export all used-track credits with source/license links and actual changes;
   verify final dialogue, cue timing and encoded loudness/peaks.

The pool is NOT wired into automatic multi-track selection or the fixed
EP01 comparison renderer. Do not silently expand the frozen A/B asset pool.
The existing renderer still needs explicit plans and verified multi-track
export/credits support before using several catalog tracks in one episode.

## Evidence and rights

Original downloaded MP3s, source-page snapshots, licensing snapshots and
measurement logs live under ignored `assets/episode_post/local/music/`.
The existing Undertow original is referenced in its prior pilot location,
without modifying or duplicating it. Copyright remains with the composer;
project-held copies are not project-owned compositions.

The first batch uses Scott Buckley's official library pages and CC-BY-4.0
attribution. Preserve his provider notices: credit in YouTube descriptions, no
isolated resale/streaming reuploads or enrollment in audio fingerprinting.
Publication still requires checking the intended platform and actual credits.
No music binaries or complete website HTML are intended for public Git.

No realtime listening has been performed. Composer descriptions and inferred
tags help discovery, but do not certify emotional fit, absence of vocals,
phrase boundaries or suitability beneath dialogue. All imported tracks remain
`TECHNICALLY_VERIFIED_AUDITION_REQUIRED` until actually auditioned.
Source masters are not delivery-normalized: some original true peaks exceed
the episode ceiling. Preserve those originals, set cue gain/ducking and verify
the finished encoded mix instead of pasting sources at unity gain.

## Verification and recovery

```bash
python3 scripts/episode_post/verify_music_library.py --decode
```

The small import tool uses reviewed official links only, preserves originals
and refuses an existing catalog. Do not rerun it to overwrite annotations.
On another checkout, restore local files from the project media backup or the
catalog's official download URLs, then require matching hashes. Changed remote
bytes need a separately reviewed version, not a silent hash update.

## Second batch: Kevin MacLeod / Incompetech

`selection-batch-02.json` adds a second composer and textures missing from the
first batch. The official site's `pieces.json` is the same catalog loaded by
its track pages; its current track-page and license-page attribution templates
specify CC-BY-4.0. Local snapshots preserve these exact source documents. Do
not substitute license wording from a third-party mirror or copy Scott
Buckley's provider-specific notices onto Kevin MacLeod's entries.

| Works | Candidate dramatic use |
|---|---|
| Jazz Brunch, Airport Lounge | Cafe, office, relaxed conversation |
| Bossa Antigua | Leisure, travel, relaxed date |
| Local Forecast - Elevator | Awkward waiting, deadpan comedy |
| Carefree | Optimistic daily life, family montage |
| Sneaky Snitch, Investigations | Comic secrets and small misunderstandings |
| Fluffing a Duck | Visual jokes and slapstick |
| Funky Chunk | Confident entrance, rhythmic montage |
| Exhilarate | Fast rock action and pursuit |
| Dream Culture | Dreams, memories, soft transitions |
| There is Romance | Tender or romantic moments |
| Heartbreaking | Loss, regret and intimate sadness |
| Desert City, Dub Eastern | Stylized travel, percussion, low-key intrigue |
| Space Jazz | Playful electronic or futuristic scenes |

Incompetech BPM/feel fields are explicitly provider metadata, not independent
beat tracking or listening verdicts. The elevator version is intentionally
filtered; Fluffing a Duck contains two short versions inside one file. Check
these intentional structures before cutting or classifying them as defects.
Regional-sounding names do not certify cultural authenticity.

Batch import preserves the prior catalog under `history/`, appends entries
without replacing original annotations, validates old and new asset hashes,
and stops if the catalog changes concurrently. Neither batch changes the
existing A/B comparison contracts or episode renders. All second-batch
entries also remain audition-required; broader composer and culturally
specific instrument coverage can be added later.
