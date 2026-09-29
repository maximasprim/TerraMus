# Frontend design notes

Design plan for `apps/web`, following the two-pass process (plan → critique →
build) rather than reaching for defaults.

## Subject
A commercial livestock ERP for a Kenyan farm business - the audience is farm
owners/managers and sales staff, not consumers. The UI needs to read as
serious operational software (an owner is checking herd value and monthly
profit, not browsing a lifestyle brand), while avoiding the generic
"enterprise SaaS blue dashboard" look that says nothing about agriculture,
and avoiding the three AI-generated-design tells named in the frontend-design
skill (warm-cream-plus-terracotta-serif, near-black-plus-acid-accent,
broadsheet-hairline). In particular the accent color deliberately avoids the
`#D97757`-family warm-clay tell.

## Token system
- **Paper** `#F7F3EA` - warm bone background, not the exact `#F4F1EA` cliché.
- **Forest** `#1F3A2E` (+ `dark`/`light`) - deep bottle-green, evoking
  highland pasture/dairy country rather than SaaS blue.
- **Brass** `#B8862B` - the accent: dry-season grass, brass ear-tags and cow
  bells. A deliberately different hue family from the common AI-generated
  terracotta accent.
- **Ink** `#201F1B` - near-black warm charcoal for text.
- **Clay** `#A6432E` (errors) and **Moss** `#3F6B4A` (success) - functional
  colors kept distinct from the brass accent so status and emphasis never
  compete for the same hue.
- **Hairline** `#E4DCC8` - warm border color instead of a cool gray.

## Type system
Three roles: a characterful serif for display (**Fraunces** - ledger/brand
warmth, used with restraint on headings only), a clean grotesk for body/UI
(**IBM Plex Sans** - chosen over Inter specifically to avoid the most common
default), and a monospace for anything that's effectively ledger/tag data
(**IBM Plex Mono** - animal IDs, weights, currency figures where alignment
matters).

**Environment note:** this sandbox can't reach `fonts.googleapis.com` (same
network constraint documented for the M-Pesa/Stripe payment providers in
`apps/api`), so `next/font/google` fails at build time here. `globals.css`
defines the three font-role CSS variables with system-font fallbacks instead,
preserving the three-role structure (serif display / sans body / mono data)
even though the specific typefaces aren't the intended ones in this build.
Swapping in the real `next/font/google` calls is a single-file change
(`app/layout.tsx`) once this runs somewhere with network access - nothing
else in the codebase references font loading.

## Layout
Fixed dark-forest sidebar (organization name in the display face, nav below)
next to a light paper content area - the one deliberate high-contrast moment
in an otherwise quiet, restrained palette, so the sidebar reads as "the farm's
own color" against neutral working space.

## Signature element
The **ear-tag chip** (`components/ui.tsx` → `TagChip`): every `animal_number`
in the UI renders as a small stamped chip - monospaced ID, a brass
hole-punch dot, a hairline border - evoking the literal physical tag every
animal in the system wears. This is the one recognizable, repeated motif
tying the visual language directly to the subject matter, used consistently
in the livestock table and the animal detail header rather than invented once
and abandoned.

## Restraint
No page-load animation, no decorative gradients, no numbered-step markers
(nothing in this UI is actually a sequence). Status pills use color
sparingly and consistently (one hue per animal status, drawn from the same
token palette, never introducing new colors ad hoc).
