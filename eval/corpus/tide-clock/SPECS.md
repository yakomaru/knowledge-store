# Tide Clock — Design Specs

## Concept

A single-screen ambient display showing the current tide state and the next two
turns for one station. No interaction beyond picking the station once.

## Tech stack

Vanilla JS, canvas for the dial, no framework and no build step. The whole thing
is three files served statically, which is the point.

## File structure

```
tide-clock/
├── index.html
├── clock.js      dial rendering + animation loop
└── tides.js      harmonic prediction + station data
```

## Physics constants

The dial animates against a notional twelve-hour-twenty-five-minute lunar cycle.
The constants that matter are the semidiurnal period of 12h25m, the station's
mean range, and the phase offset that aligns the prediction to local high water.

## Harmonic prediction

Tide height is the sum of a small number of harmonic constituents. Four is enough
for an ambient display: the two semidiurnal and the two diurnal terms. Adding more
constituents improves accuracy by less than the dial can render.

## Animation loop

One `requestAnimationFrame` loop that recomputes height only when the minute
changes, and interpolates the dial position between those recomputations. The
prediction is cheap but not free, and running it every frame heats the laptop for
no visible gain.

## Rendering the dial

The dial is drawn once to an offscreen canvas and blitted each frame with only the
hand redrawn. Redrawing the tick marks and labels every frame was the entire cost
of the first version.
