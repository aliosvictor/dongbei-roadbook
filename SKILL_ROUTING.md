# SKILL_ROUTING.md
Spec version: v5

This file contains only explicit repository-specific skill-routing overrides. It is a stable policy file, not a session inventory, task plan, or activity log.

## Repository-specific overrides

### Current travel deep research

- Task signal: the user explicitly requests Deep research, explicitly says "深度研究", or selects Deep research mode for current foliage, weather, road, park-access, border, fire-control, or drone conditions.
- Exact skill name: `deep-research-work:deep-research`.
- Scope or exclusion boundary: use it for time-sensitive travel evidence and route decisions. Do not trigger it for ordinary wording edits, deterministic map regeneration, local consistency checks, or a quick factual lookup.
- Required project-specific verification: prefer dated official primary sources for rules and status; use domestic travel platforms as practical-experience evidence; separate current notice, forecast, seasonal norm, visitor report, and inference; audit every affected plan and update `sources.qmd` when changes are authorized.

### PDF deliverables

- Task signal: the user explicitly asks to create, restore, export, inspect, or validate a PDF version of the roadbook.
- Exact skill name: `pdf`.
- Scope or exclusion boundary: apply only to the requested PDF artifact. The maintained default is the Quarto website; do not recreate the former slides or Overleaf workflow merely because PDF tooling is available.
- Required project-specific verification: confirm page count, render every page to images, inspect maps and text boundaries, run structural PDF validation when available, and retain only the requested final PDF rather than duplicate build outputs.

### Generated scenic artwork

- Task signal: the user asks for a new AI-generated cover, illustration, or photographic-style bitmap asset.
- Exact skill name: `imagegen`.
- Scope or exclusion boundary: use it for creative raster artwork only. Never use it to generate or correct route maps, geographic coordinates, road geometry, map labels, or factual photographs of a claimed location; use `data/itinerary.json` and `scripts/build_maps.py` for maps.
- Required project-specific verification: inspect the final bitmap at intended display size, confirm it introduces no false factual label or access claim, optimize its web format and dimensions, and verify the rendered page on desktop and mobile.

## Entry contract

Add an entry only when the repository requires a concrete task signal to use a named skill or imposes a routing exception that cannot live in that skill. Each entry must state:

- task signal
- exact skill name
- scope or exclusion boundary
- required project-specific verification

If no listed entry matches, no repository-specific override applies; follow `AGENTS.md` and the selected skill's own instructions.

## Maintenance

- Update this file only when an override is added, changed, or removed.
- Keep general agent behavior, changing skill inventories, model configuration, progress, assumptions, execution history, and workflow instructions out of this file.
- Keep detailed procedures, scripts, dependencies, and examples inside the relevant skill.
