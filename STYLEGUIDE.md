# Open Beverly — Style Guide

A reference for writing style and design principles used across this site. This guide exists to keep the site consistent, credible, and accessible to Beverly residents regardless of their background in municipal finance.

---

## Editorial Process

- **Always confirm copy with Alaina before pushing.** Draft content for review first. Do not commit and push prose changes until the copy has been explicitly approved.

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
- All quantitative figures must come from an official city document, state agency, peer-reviewed source, or credible news reporting, and must be cited.
- Distinguish clearly between figures drawn directly from official documents and figures calculated by Open Beverly.
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
Note: the class name is a legacy artifact from the City Hall section; it is used broadly as a general neutral callout. Neutral info icon (`fa-circle-info`), white background with blue border. Used to summarize the key context of a section without advocating. Never use a checkmark; never use language that directs the reader to a conclusion.

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

### Charts and Graphs

**Library:** Chart.js 4.4 (`chart.umd.min.js` via jsDelivr CDN).

**General principles:**
- Charts support the data; they do not replace it. Every chart should have a title, a subtitle explaining the unit and scope, and a data table fallback for screen readers.
- Use the site color palette. Do not introduce new colors for charts without adding them to the palette.
- All charts must be `responsive: true` and `maintainAspectRatio: false` with a defined container height.
- Gridlines: horizontal only on line and bar charts, color `#e2e5ea`. No vertical gridlines.
- Tick labels: `font-size: 11px`, color `var(--muted)`.
- Tooltips: format values consistently with axis labels (same units, same precision).
- Legends: only shown when a chart has more than one dataset. `boxWidth: 12`, `font-size: 11`.

**Line charts:**
- Used for trends over time (tax rates, levy growth, deficit trajectory).
- Open Beverly navy (`#1a2744`) for the primary series. Accent orange (`#e8813a`) for a secondary or projected series.
- No fill under the line unless the fill meaningfully adds information.
- Points shown; no point labels on the chart itself (use tooltips).

**Bar charts:**
- Used for comparisons across categories or years.
- `borderRadius: 4` on bars. Never use 3D or shadow effects.
- Single-series bars: use navy or blue. Multi-series: navy + accent, or navy + muted.
- Horizontal bar charts for category comparisons where labels are long (e.g., peer city comparisons).
- Beverly highlighted in accent orange when shown alongside peer cities.

**Donut charts:**
- Used for part-to-whole relationships (e.g., budget breakdown by department).
- Maximum 6 segments. Combine smaller categories into "Other" if needed.
- No labels directly on the chart; use a legend or data table below.
- Center text optional for a key total figure.

**Accessibility:**
- Every `<canvas>` has `role="img"`, `aria-labelledby` pointing to the chart title, and `aria-describedby` pointing to a visually hidden data table.
- Data tables are generated programmatically alongside every chart (`addChartDataTable`).

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
