# Beverly Data — Style Guide

A reference for writing style and design principles used across this site. This guide exists to keep the site consistent, credible, and accessible to Beverly residents regardless of their background in municipal finance.

---

## Writing Style

### Voice and Tone
- **Factual and nonpartisan.** The site presents data and context, not conclusions. Let the numbers speak.
- **Casual but credible.** Written for Beverly residents, not policy experts. Accessible language without being condescending.
- **Not advocacy.** Frame issues using data and documented sources. Avoid language that tells readers what to think or feel.
- **Let readers draw their own conclusions.** Present the facts, the tradeoffs, and the context. Trust the reader.

### Rules
- **No em dashes.** Ever. Use a colon, comma, or rewrite the sentence.
- **No "significant" as a vague intensifier.** Use specific numbers or omit.
- **No unsourced claims.** Every quantitative claim must be traceable to a primary source or clearly labeled as an estimate.
- **No hedging with "typically" or "generally" unless sourced.** If a range or pattern is documented, cite it. If it isn't, soften or remove the claim.
- **Soften rather than remove contested claims.** If something can't be sourced precisely, acknowledge the uncertainty rather than cutting the point entirely.
- **No "how we grow" framing.** Avoid language that implies a prescribed direction for the city's development.
- **No relative dates.** Use absolute dates (e.g., "December 2025" not "last year").

### Sourcing Standards
- All quantitative figures must come from an official city document, state agency, peer-reviewed source, or credible news reporting — and be cited.
- Distinguish clearly between figures drawn directly from official documents and figures calculated by Beverly Data.
- Estimates must be labeled as estimates, with methodology explained.
- If a source cannot be found, soften the language rather than asserting the claim.
- The Beverly Beat is an acceptable source for local reporting. Attribute quotes and facts to it explicitly.

### Framing
- The Strong Towns revenue-per-acre framework informs the site's analysis of land use and fiscal productivity, but is cited as a reference rather than used as an organizing argument.
- The structural deficit is explained as a math problem (cost growth vs. revenue cap), not a spending problem or a mismanagement problem.
- Capital budgets and operating budgets are different things. Make this distinction explicit whenever a capital project comes up in a fiscal context.
- One-time revenues (asset sales, reserve draws) cannot fix a structural deficit. Say this clearly.

---

## Design Principles

### Overall Philosophy
- **Clarity over cleverness.** Every design element should help readers understand the data, not impress them.
- **WCAG AA compliance required.** All text must meet 4.5:1 contrast ratio minimum. UI elements and large text must meet 3:1 minimum.
- **No animation beyond functional transitions.** Hover states are simple flips (e.g., outlined to filled), not motion-heavy effects.

### Color Palette
| Variable | Hex | Use |
|---|---|---|
| `--navy` | `#1a2744` | Primary text, headings, nav, section titles |
| `--blue` | `#2d5fa8` | Links, interactive elements |
| `--accent` | `#e8813a` | Orange; highlights, stat numbers, card top borders |
| `--bg` | `#f5f6f8` | Page background |
| `--muted` | `#5d6472` | Secondary text, labels, metadata |
| `--border` | (light gray) | Card borders, section dividers |
| `--tag-bg` | (light blue-gray) | Tag and callout backgrounds |
| `--warn-bg` | (light amber) | AI notices and warning callouts |

### Typography
- Body text: `0.9rem`–`0.95rem`, line-height `1.7`–`1.75`
- Section titles: `1.35rem`, weight `800`, navy, with bottom border
- Muted metadata: `0.78rem`–`0.82rem`, color `var(--muted)`
- Footnote refs: `0.7em`, superscript, color `var(--blue)`, weight `700`
- Back-to-top links: `0.875rem` (14px minimum), color `#3f4550` (~7.5:1 contrast)

### Component Patterns

**Structural box** (`.structural-box`)
Used for explainer content: context, caveats, background information. Blue left border. Used when the content is explanatory rather than data.

**Callout box** (`.not-waste` inside `.structural-box`)
Neutral info icon (`fa-circle-info`), white background with blue border. Used to summarize the key takeaway of a section without advocating. Never use a checkmark; never use language that tells the reader what to conclude.

**AI notice** (`.ai-notice`)
Amber background, orange left border. Used only for AI-generated content warnings (meeting summaries page). Prominent, not dismissible.

**Jump navigation** (`.page-nav`)
Pill-shaped links, navy text on white with navy border. On hover: white text on navy background, no animation. Must explicitly set `border-bottom` to override global nav styles.

**Back-to-top links** (`.back-to-top`)
Right-aligned, `0.875rem`, color `#3f4550`. Appear after each major section. Link to `#main`.

**Footnotes**
Pattern: `<a href="#fn-N" id="fnref-N" class="fn-ref">[N]</a>` inline, with back-links (`↩`) at the bottom of the page. Used for sourcing claims that need more detail than inline text allows.

**Stat chips**
Used in hero sections for key numbers. Value in accent orange, label in muted white. Don't use for unverified estimates.

### Page Structure
- Every page has: skip link, shared nav (nav.js), page header or hero, main content, footer with AI disclosure.
- Footer always includes: independence disclaimer, AI assistance disclosure, data source attribution.
- Nav includes: Meetings dropdown, Finance dropdown, Property Map, Sources, About.
- All pages link to Sources and About in the nav.

### Icons
Font Awesome 6 (kit `56a48e0c30`). Use semantic icons that match the content. Prefer `fa-circle-info` for neutral informational callouts. Never use checkmarks to imply correctness or approval.

---

## Accessibility

- All pages include a skip link (`<a href="#main" class="skip-link">`).
- `<main>` always has `id="main"`.
- Nav dropdowns use `aria-haspopup` and `aria-expanded`.
- All icons used decoratively include `aria-hidden="true"`.
- Jump nav includes `aria-label="Page sections"`.
- Color alone is never used to convey meaning.
- Minimum touch target size: `44px` for interactive elements.

---

## What This Site Is Not

- Not affiliated with the City of Beverly or any advocacy group.
- Not a source of legal or financial advice.
- Not a record of city proceedings (official minutes are authoritative).
- Not an AI-generated site published without review (except meeting summaries, which are clearly labeled).
