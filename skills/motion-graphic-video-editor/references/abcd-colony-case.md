# Worked example: a 35-second event countdown film

> **作者示例案例（第三方品牌，仅作拆解学习）。** 品牌名、Logo、配色与文案均属原品牌方，不可直接套用；可迁移的只是剪辑结构与方法。

A complete build, from a reference clip and a brand book to three delivered
aspect ratios. Included because it is more useful to see one real timeline and
one real revision loop than to read another abstraction. The brand here is a
Web3 event IP; the same shape works for a product launch, a funding announcement
or a conference teaser.

## The brief

A reference clip (a DEX's "$20M in volume" promo, 9.35s), a brand identity PDF,
a logo PNG, an event name, dates and a URL. The ask: "extract the editing method
from this reference, then make me one."

## Step 1 — what the reference actually was

`analyze_reference.py` on the clip: 1920×1080, 60fps, 9.35s, and exactly **one**
audio transient, at 0.47s. That single fact defined the whole approach — the film
had one hard cut and everything else was easing.

The structure, in five beats:

| time | segment | what happens |
|---|---|---|
| 0.00–0.60 | tension | black, a single dim point breathing at centre |
| 0.60–1.80 | burst | point explodes into a glowing ring; product art flies out with radial blur; the one impact |
| 1.80–4.80 | payload | camera pushes through the debris; a slot-machine counter rolls to the headline number and locks |
| 4.80–6.60 | breath | hard cut to black; a one-line claim revealed by a gradient sweep |
| 6.60–9.35 | resolve | logo lockup returns in a glow ring; CTA lines appear; breathe out |

Named as a formula: **tension → burst → payload → breath → resolve.** That is
what transfers; the Pokémon card packs do not.

## Step 2 — what the brand book gave

Seven spectrum hues with exact stop positions, an ink/paper/muted set, a
display/body/mono type trio, a "rounded block" graphic system, and a hard rule
that the gradient is always horizontal, left to right, cool to warm.

The substitutions that made it the brand's film rather than a copy:

- Reference's flying product art → the brand's **rounded blocks**, with ~18% of
  them carrying the brand's own letterforms.
- Reference's single-hue glow ring → a **full spectrum ring** in brand order,
  treated as environmental light rather than as the logo gradient (which the
  guidelines forbid using radially).
- Reference's four-second counter → same mechanism, brand number.
- New middle section with no reference equivalent: the brand's four naming
  pillars as full-screen letterform cards. Worth adding because it gave the film
  something to say in its middle, and it used an asset nothing else did.

## Step 3 — the timeline

120 BPM, beat 0.5s, bar 2.0s, 18 bars.

| time | bar | section |
|---|---|---|
| 0.00–2.00 | 1 | tension: dim point, riser |
| **2.00** | 2 | **burst** — ring, blocks, streaks, impact |
| 4.20 | 3 | lockup fades in above centre |
| 6.00 | 4 | counter starts rolling |
| **8.00** | 5 | **counter locks**, colour switches to paper white |
| 8.50 / 9.10 / 9.60 | 5 | headline, divider, date appear in sequence |
| 11.62 | 6 | countdown card clears |
| 12.00–16.00 | 7–8 | four letterform cards, one per second |
| 16.00–19.52 | 9–10 | statement, swept, on black — the breakdown |
| **20.00** | 11 | **3D lockup reveal** — the drop |
| 21.42–22.56 | 11–12 | event name decodes beside the mark, then materialises in 3D |
| 23.20 | 12 | lockup shrinks and moves to the upper third |
| 23.70–25.90 | 13 | card 1: the dates |
| 26.20–28.46 | 14 | card 2: the URL |
| 28.58–31.30 | 15 | card 3: the tagline |
| 31.78 | 16 | through black |
| 32.00–33.65 | 16–17 | logo alone, held |
| 33.65–35.00 | 17–18 | fade out |

Six landmarks land exactly on bar lines. That is what makes the score trivial and
the film feel deliberate.

## Step 4 — the revision loop

This is the part worth studying, because the notes were completely predictable in
hindsight and the fixes generalise.

**v1 — 12s, three aspect ratios.** Feedback: *"6/10. The ending is too crowded,
too much text. Extend to 20–30s so the important information stays longer. Add a
3D effect for the name."*

The single most likely note on any first cut. Five CTA lines stacked on one
screen read as a slide. Fixes: extend to 30s; split the ending into sequential
cards sharing one position, 2.2–2.7s each; build a real extruded 3D lockup;
replace the sound-effects bed with a full arrangement.

**v2 — 30s.** Feedback: *"v1 looked better. The circular glow has a square frame
around it, which is meaningless and strange."*

An artifact I introduced while optimising: I had baked the glows into PNGs for
speed, and the ring was wider than its canvas. Screen-composited, the texture's
square edge was visible — edge-midpoint brightness measured (121,19,49). Fixed by
padding the canvas, forcing the border to zero, and scaling the display size back
up. Also took the chance to close the ring properly with a shaded return arc.

**v3.** Feedback: *"At 29s hold two more seconds before fading. The number is
cropped top and bottom — would a digital font look better?"*

Two real bugs and a design question. The reel window was exactly one cell tall,
so neighbouring digits were hard-cropped into fragments. Fixed with a taller
window plus a speed-linked mask. For the font, I rendered a six-way comparison
still on the brand background rather than arguing — the client picked Orbitron in
under a minute. **Showing beats describing**, and a comparison still costs
seconds against a 15-minute render.

**v4.** Feedback: *"The a/b/c/d letters use too ordinary a font."*

Correct, and the fix was sitting in the brand asset the whole time: cut the four
letterforms out of the logo instead of setting them in the display face. They
carry their own gradient segment and modular construction, so they are
unmistakable — and no font in the world matches a custom mark.

**v5.** *"At 22s, the name should have a decode effect. Don't touch the mark."*

Built with the brand's own glyphs as the scramble pool, which required splitting
the lockup into two independent extrusion stacks. This is why splitting the
lockup early is worth it — retrofitting meant rebuilding the 3D layer.

**v6, v7.** URL change; `july` → `July`; a logo fade-out ending. Each a constant
plus a re-render — which is the point of parameterising everything.

## What the loop teaches

1. **Every first cut is too crowded and too fast.** Budget for a 1.5× duration
   increase and sequential cards from the start.
2. **The client's diagnosis is usually a symptom; find the cause.** "v1 looked
   better" meant one specific artifact, not a rejection of the new structure.
3. **Show, don't argue, on subjective calls.** A comparison still is cheap.
4. **Reach for the brand's own assets before reaching for a font.**
5. **Batch notes.** Every change is a 15–25 minute render, so verify with a
   contact sheet and collect the round's feedback before committing.
6. **Parameterise everything a client can name.** Numbers, dates, URLs, copy
   capitalisation, fonts, duration, aspect. All of them were asked for.

## Final spec

35.0s, 60fps, 18 bars at 120 BPM. 1920×1080 and 1080×1920 delivered
(2100 frames each, ~17 min render on 2 cores, ~13 MB at CRF 17). Score
synthesised to 35s with a breakdown at bar 9–10 and the drop at bar 11.
Everything driven by a single `T = {...}` timeline object and about a dozen
string constants.
