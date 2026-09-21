# Motion recipes

Implementations for the effects that carry a brand film. Each has a short note
on *why* it is built that way — the construction usually matters more than the
parameters, and knowing the reason lets you adapt it instead of copying it.

## Contents

1. [Gradient sweep text reveal](#1-gradient-sweep-text-reveal)
2. [Slot-machine counter](#2-slot-machine-counter)
3. [3D extruded logo](#3-3d-extruded-logo)
4. [Decode / scramble text](#4-decode--scramble-text)
5. [3D particle tunnel with depth of field](#5-3d-particle-tunnel-with-depth-of-field)
6. [Burst: ring, core, streaks](#6-burst-ring-core-streaks)
7. [Staged information cards](#7-staged-information-cards)
8. [Brand letterform cards](#8-brand-letterform-cards)
9. [Corner brackets and dividers](#9-corner-brackets-and-dividers)
10. [Transitions](#10-transitions)

---

## 1. Gradient sweep text reveal

The effect people read as "high production value". It is not a typewriter — it is
**colour, blur and vertical offset moving together** as a soft edge scans across
the line. Each character arrives blurred, low and tinted, then settles sharp,
level and light. Doing only opacity looks cheap; the three-channel version is
what sells it, and it costs the same.

```js
function sweepChars(o, t, t0, dur, mode, outK){
  const n = o.spans.length, EDGE = 0.30;        // width of the soft edge
  const sw = eOut(seg(t, t0, t0+dur)) * 1.30;   // >1 so the last char completes
  for(let i=0;i<n;i++){
    const p = n>1 ? i/(n-1) : 0;                // position along the line
    const q = cl((sw - p) / EDGE);              // this char's progress
    const s = o.spans[i];
    s.style.opacity   = sstep(0, 0.55, q) * (1-outK);
    s.style.color     = rgba(mixc(specRGB(p), PAPER_RGB, sstep(0.22,1,q)), 1);
    s.style.transform = `translateY(${(1-q)*14*S}px)`;
    s.style.filter    = q<0.98 ? `blur(${(1-q)*6*S}px)` : 'none';
  }
}
```

`mode` variants worth having: `hot` (spectrum hue settling to paper white — best
for statements), `spectrum` (stays in brand colour — best for URLs and numbers),
`none` (inherits, for small mono labels).

Two details that matter. `EDGE = 0.30` means about a third of the line is
mid-transition at any moment; much tighter reads as a wipe, much looser and the
line just fades. And letter-spaced text needs `text-indent` equal to the
letter-spacing, or the trailing space pushes the line off-centre.

---

## 2. Slot-machine counter

A column of digits translated vertically inside a masked window. What makes it
read as a mechanism rather than a crossfade is that **each place spins a
different number of whole turns**, so they settle at different speeds.

Build 90 cells (0–9 repeated) so the reel never runs out. Position is a
continuous count of cell heights, which means the digit at rest is
`total % 10` — so choose the total as `wholeTurns*10 + targetDigit`:

```js
const totalTens = 30 + tensDigit;   // 3 turns
const totalOnes = 60 + onesDigit;   // 6 turns
const spin = eExpo(seg(t, spinStart, lockTime));
let vT = totalTens*spin, vO = totalOnes*spin;

// settle bounce
const sb = seg(t, lockTime, lockTime+0.34);
if(sb>0 && sb<1){ const b = Math.sin(sb*Math.PI)*(1-sb)*0.16; vT -= b; vO -= b*1.5; }

reel[0].style.transform = `translateY(${REEL_OFF - vT*DIGIT_H}px)`;
```

Three supporting touches:

- **Speed-linked mask.** The window is ~1.3× a cell tall with a top/bottom
  falloff whose width is `(1-spin)*0.19` — soft while moving, exactly zero once
  locked. See the reel entry in `gotchas.md` for why both the height and the
  speed-linking are needed.
- **Motion smear.** `blur((1-spin)² * 22px)` on the wrapper. Squared so it
  disappears sharply as the reel settles.
- **Colour change on lock.** Two identical stacked reels, one filled with the
  brand gradient and one solid white, cross-faded over 0.3s at the lock. The
  number arriving *in brand colour* and settling to white is a strong beat.

Font choice is a real decision. A geometric/techno face (Orbitron, Chakra Petch)
reads as digital; a true seven-segment face (DSEG) reads as a clock but clashes
with most modular brand marks and its `1` is a bare stroke. Measure the digit
advance ratio and derive the cell width from it — faces vary from 0.54 to 0.83 em
and a hardcoded width will crowd or scatter.

---

## 3. 3D extruded logo

Stack many Z-offset copies of the artwork with a brightness ramp. The visible
side wall is the sliver of each slab not covered by the one in front, so the
stack renders as a shaded solid.

```html
<div id="wrap">                                   <!-- opacity lives here -->
  <div id="stage" style="transform-style:preserve-3d">
    <div id="body" style="transform-style:preserve-3d">
      <!-- deepest first -->
      <img class="slab" style="transform:translateZ(-123px)">
      ...
      <img id="front">                            <!-- painted last -->
    </div>
  </div>
</div>
```

```js
body.style.transform =
  `perspective(${1500*S}px) translateZ(${tz}px) rotateX(${rx}deg) rotateY(${ry}deg)`;
```

Parameters that work: ~40 slabs, step ≈ 0.3% of display width (total depth
≈ 12%), perspective 1500·S, rotation from −48° settling to −13°, tilt 13° → 5°.

Four things will bite you, all detailed in `gotchas.md`: any blend mode, group
opacity or filter inside the preserve-3d subtree flattens the whole thing; the
ramp must stay bright enough to see (0.58 → 0.18); hairline text combs and
should be cut out of the slab source; and `easeOutExpo` on the rotation is over
before it registers — use a slower cubic.

Finishing touches worth the effort: a specular sweep (a white gradient masked by
the logo's alpha, its `background-position` animated across) reads as a light
raking over a solid surface. Two coloured rim-light glows behind, in the brand's
end hues, separate the logo from the background. A floor reflection is usually
*not* worth it — it competes with the extrusion and reads as a smudge.

---

## 4. Decode / scramble text

Characters cycle through random glyphs and resolve left to right. The version
that looks best uses **the brand's own letterforms as the scramble pool**, cut
from the logo — so every intermediate frame is still on-brand, with none of the
"wrong font" feeling a substitute face gives.

```js
const POOL = ['C','O','L','N','Y'];          // unique glyphs from the word
for(let i=0;i<slots.length;i++){
  const lockT = decodeStart + i*0.115;       // resolve one every ~7 frames
  if(t >= lockT){
    setGlyph(slots[i], slots[i].target);
    const fl = imp(t, lockT, 0.20, 2.0);     // brief flash as it locks
    slots[i].el.style.filter = `brightness(${1+1.5*fl}) drop-shadow(0 0 ${16*fl}px #00D8FF)`;
  } else {
    const tick = Math.floor(t*FPS/2);        // new glyph every 2 frames
    const h = (tick*2654435761 + i*40503) >>> 0;   // deterministic hash
    setGlyph(slots[i], POOL[h % POOL.length]);
    slots[i].el.style.opacity   = 0.30 + 0.55*(((h>>>13)%100)/100);
    slots[i].el.style.transform = `translateY(${((((h>>>7)%100)/100)-0.5)*4*S}px)`;
  }
}
```

Position each slot by its centre from the source artwork and centre whichever
glyph is showing inside it, so varying glyph widths do not cause jitter.

Sequencing it with a 3D lockup: let the mark land and settle alone first, then
decode the word beside it as flat glyphs, then materialise the extruded version
over ~0.16s with a small flash. The flat glyphs and the 3D front face are the
same image in the same place, so the switch is invisible — only the depth
appears, which lands as "it became real".

Sound helps disproportionately here: a fine high-frequency click texture at
~30 Hz during the scramble plus one rising chime per resolved character.

---

## 5. 3D particle tunnel with depth of field

Particles in a depth range, camera pushing through, depth-of-field blur, and the
brand's own graphic shapes as the particles. Use the shapes from the brand's
graphic system (rounded blocks, chevrons, whatever the guidelines define) — a
tunnel of brand-native shapes is far better than generic bokeh, and some of the
particles can carry the brand's letterforms.

Project the perspective in JS rather than using CSS 3D, because depth-of-field
needs container filters and a container filter breaks `preserve-3d`:

```js
let z = z0 + camZ;
while (z > Z_NEAR) z -= (Z_NEAR - Z_FAR);          // recycle, same span as spawn
const sc = PD/(PD - z);
const x = Math.cos(ang)*R*sc*S, y = Math.sin(ang)*R*0.86*sc*S;
// tumble: 2D rotate plus axis foreshortening — indistinguishable from real 3D here
const fx = 0.12 + 0.88*Math.abs(Math.cos(angY));
const fy = 0.12 + 0.88*Math.abs(Math.cos(angX));
el.style.transform = `translate(${x}px,${y}px) rotate(${angZ}deg) scale(${sc*fx},${sc*fy})`;
```

Depth of field via **depth-sliced containers**: 10–16 divs, each with one fixed
blur set from its slice's distance to the focal plane, and particles reparented
only when their slice changes. Paint order far → near gives correct occlusion.
This is the difference between 1 fps and 2.5 fps; per-element blur is the single
most expensive thing you can do.

Fade particles at both ends of the range (`smoothstep` in and out) so nothing
pops, and let ~18% of them carry a letterform and ~32% be outline-only for
variety. During the burst, apply one motion smear to the whole container rather
than per element.

---

## 6. Burst: ring, core, streaks

The impact frame. Three layers, all pre-rendered or trivial:

- **Ring** — spectrum donut PNG, scale 0.10 → 1.00 with `easeOutExpo` over
  0.34s, then a slow drift and a slight dim.
- **Core** — hot white/cyan blob, scale 0.34 → 2.1, opacity decaying to 0 over
  0.55s. It should be gone before the eye settles.
- **Streaks** — ~16 rounded bars radiating out, `background: linear-gradient(90deg, hue, transparent)`,
  width 0 → full with `easeOutExpo`, opacity `1-p^1.5`, each with a small random
  delay. Blend `screen`.

Plus a radial flash on the overlay layer via `imp()`, and one hard audio
transient on the same frame. Resist adding more hard cuts than the reference
has — a single decisive impact reads as confidence; several read as a trailer.

---

## 7. Staged information cards

The fix for "the ending is too crowded". Instead of stacking five lines, show
one message at a time in the same screen position, each holding 2–3 seconds:

```js
const windows = [[c1In, c1Out], [c2In, c2Out], [c3In, c3Out]];
cards.forEach((c, i) => {
  const [a, b] = windows[i];
  if(t < a-0.05 || t > b+0.30){ c.g.style.opacity = 0; return; }
  const outK = seg(t, b-0.28, b+0.06);
  c.g.style.opacity = 1;
  c.g.style.transform = `translate(-50%,-50%) translateY(${-outK*22*S}px)`;
  sweepChars(c.label, t, a,      0.42, 'none', outK);
  sweepChars(c.value, t, a+0.16, 0.62, c.mode, outK);
});
```

Each card is a small mono label above a large display value. Keep the brand
lockup persistent above the card slot so brand presence never drops. The card
exits by drifting up and fading rather than cutting, which keeps the rhythm calm.

If a client says the ending is rushed, the fix is to *lengthen the film*, not to
compress the cards. Two seconds per message is the floor.

---

## 8. Brand letterform cards

Full-screen single-letter cards (a pillar, a value, an initial). Use the letter
cut from the logo, never a typeface — it carries the brand's construction and
its slice of the gradient for free, and it is unmistakable.

```js
const L = document.createElement('img');
L.src = `assets/glyph_${ch}.png`;
L.style.cssText = `display:block;width:auto;height:${404*TS}px`;
L.style.filter = `drop-shadow(0 0 ${28*S}px ${hue}99) drop-shadow(0 0 ${76*S}px ${hue}44)`;
```

Crop all letters against one shared vertical band (`logo_tools.py letters` does
this) so ascenders stay tall and x-height letters stay short. Displaying them at
equal height then preserves real proportions and a common baseline. Cropping
each to its own bounding box makes `a` and `c` look oversized next to `b` and
`d` and immediately reads as wrong.

One second per card with a hard cut between them is a good rhythm; half a second
is too fast to read the supporting word.

---

## 9. Corner brackets and dividers

Cheap, and they make a black frame feel designed rather than empty.

**Corner brackets** — four divs inset from the frame edges, each with two
borders and a rounded corner, in the section's hue, fading in with the content.

**Spectrum divider** — a flex row of small rounded bars in brand order,
revealed with `scaleX(0.2 → 1)`. Use it to close a stack of text.

**Pixel field** — a `radial-gradient` background tiled at ~46px with a 1.7px dot
at 16% opacity, drifting slowly. Gives black some texture at nearly zero cost.

---

## 10. Transitions

**Hard cut through black.** Three frames of black between sections. Cleaner than
a dissolve and it gives the eye a reset. Implement as a spike on the fade layer:

```js
const cut = (a,w) => { d = Math.max(d, 1 - cl(Math.abs(t-a)/w)); };
cut(sectionStart - 0.05, 0.08);
```

**Cross-fade through black.** For a bigger gear change (a film's last act), a
wider version of the same spike — ~0.3s each side — so one thing ends and
another begins rather than replacing it.

**Match hold.** Keep one element (usually the lockup) alive across a cut while
everything else changes. Maintains brand presence and makes the film feel like
one piece rather than a sequence of slides.
