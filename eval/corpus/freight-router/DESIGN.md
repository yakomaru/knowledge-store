# DESIGN.md — Frontend design philosophy

## One-line summary

Dense, quiet, and legible at a glance: an operator stares at this for eight hours,
so nothing may demand attention unless it is actually wrong.

## Forbidden patterns

No modal dialogs for anything recoverable. No spinners over data that already has
a cached value — show the stale value with a subtle freshness marker instead. No
color as the only signal, because the dispatch floor has two colorblind operators.

## Color philosophy

One accent, used exclusively for the primary action in a view. Status uses a
four-step neutral ramp plus a single alert hue. If a screen needs a fifth status
color, the information architecture is wrong.

## Type stack

System UI stack, 14px base, tabular numerals everywhere a number can change. Row
height is 28px in tables; anything taller wastes the operator's screen.

## Motion philosophy

Motion exists to show causality — where a row went, which panel opened. Nothing
animates purely decoratively, and every transition is under 150ms.
