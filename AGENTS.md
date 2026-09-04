# AGENTS.md
Spec version: v5

This file defines durable repository constraints for the Northeast roadbook. Keep reusable task procedures in skills and repository-specific skill-routing overrides in `SKILL_ROUTING.md`.

## 1. Scope and authority

- Start from the underlying travel, publishing, or maintenance goal. If the requested method is materially less direct, explain the better path before proceeding.
- For requests to answer, explain, review, diagnose, compare, or plan, inspect the relevant repository material and report the result; do not modify files unless the user requests changes.
- For requests to change, build, fix, or publish, make the smallest coherent in-scope change and run relevant non-destructive validation without seeking routine confirmation.
- Ask before destructive or irreversible actions, external writes not implied by the request, credential use not already authorized, or material expansion beyond the requested scope.
- When intent is materially ambiguous, pause only for the decision that would change the outcome. Otherwise make the smallest safe assumption and continue.
- Explicit task instructions take priority over repository defaults within the applicable instruction hierarchy and permission boundaries.

## 2. Project purpose and editorial rules

- This repository is the editable Quarto roadbook for the 2026-09-26 through 2026-10-03 Northeast self-drive trip from Qiqihar to Harbin.
- Natural scenery, scenic roads, photography value, reasonable sleep, and safe driving take priority over city sightseeing and checklist-style attraction collection.
- Treat rental-car, lodging, arrival, return, rail, and flight handoffs stated by the user as hard constraints.
- Prefer self-driving scenery when quality is comparable. A strong official scenic area may remain when its experience justifies the required shuttle or park transport.
- Keep the natural-scenery preference as an editorial rule; do not add meta commentary about that preference to the published pages unless requested.
- Published prose should describe the chosen plan and its execution directly. Do not add defensive project-history language about what was removed, corrected, rejected, or intentionally not done. Safety rules and route cutoffs may be stated directly when operationally useful.
- Do not expose internal generation notes, repository paths, script descriptions, or implementation details in reader-facing pages unless they help travelers execute the trip.

## 3. Repository structure and sources of truth

| Layer | Files | Rule |
|---|---|---|
| Editorial pages | `index.qmd`, `primary.qmd`, `option-skip-qiqian.qmd`, `sources.qmd` | These are the editable reader-facing sources. Keep route names, dates, timings, lodging, photography points, and decision rules consistent across them. |
| Route schema | `data/itinerary.json` | This is the authoritative source for map places, photo points, route control points, labels, route kinds, contexts, and daily map identifiers. |
| Generated maps | `figures/maps/*.webp` | Generate these from `data/itinerary.json` with `scripts/build_maps.py`; do not hand-edit the images. Track the resulting WebP files because the published site consumes them directly. |
| Site schema | `_quarto.yml`, `styles.css`, `assets/fonts/web/` | Keep navigation, layout, typography, loading behavior, and reader-facing labels consistent. |
| Deployment | `.github/workflows/publish.yml` | `main` contains sources; the workflow renders and publishes the site to `gh-pages`. Do not edit `gh-pages` manually. |

- `_site/`, `.quarto/`, local tools, caches, screenshots, and temporary QA artifacts are generated state and must remain untracked.
- The former Overleaf/slides workflow is not part of the current site. Do not recreate slide decks, LaTeX outputs, or duplicate PDFs unless the user explicitly reintroduces that deliverable.

## 4. Two-plan consistency

The site has two complete alternatives with parallel information architecture:

- Main itinerary: `primary.qmd`, `overview`, and `d01` through `d08`.
- Backup itinerary without Qiqian: `option-skip-qiqian.qmd`, `skip_overview`, and `s01` through `s08`.

When a change affects more than one plan:

- audit both rather than copying text mechanically
- keep the same top-level section hierarchy: summary, photography priority, sunrise/sunset reference, daily itinerary, equipment, lodging, vehicle/supplies, and daily checklist
- keep each day's endpoint continuous with the next day's starting point
- distinguish necessary access or return-road repetition from accidental backtracking
- remove duplicated fixed photography stops unless a later occurrence is explicitly a weather backup
- propagate shared corrections such as park transport, road access, vehicle pickup, safety cutoffs, and equipment guidance to every affected plan
- keep plan-specific tradeoffs visible on the corresponding plan page rather than overloading the main itinerary

## 5. Route and timing integrity

- Do not infer a drivable connection from geographic proximity or a schematic map line. Verify material connectors with current navigation, transport authority, scenic-area, or credible local information.
- Mark each route segment accurately as `drive`, `transfer`, `rail`, or `alternative`. Park shuttles and official chauffeur segments must not appear as self-driving routes.
- For restricted scenic areas, record how travelers reach the viewpoint, where their car remains, how they retrieve it, and the fallback when through-travel is unavailable.
- For unpaved, seasonal, construction-affected, border, forest-fire-control, or limited-access roads, add a concrete decision point before entering and a clear safe fallback. Avoid plans that require entering a spur and then backtracking merely to discover closure.
- Long driving days need realistic meal, fuel, driver-rest, photography-stop, congestion, and sunset margins. Use hard departure cutoffs where a late stop threatens lodging or safe arrival.
- Sunrise and sunset times are planning references, not guarantees. Recalculate them if dates or locations change and distinguish civil twilight, sunrise/sunset, and desired camera-ready time.
- Prefer one strong sunrise or sunset over several redundant events when sleep and driving safety would otherwise suffer.

## 6. Maps and photography

- Keep one complete overview map for each plan and one route map on every daily section.
- Every daily map must show both the complete-plan context and that day's segment using visibly different colors.
- Use blue points for priority photography locations and keep route nodes visually distinct from photo points.
- Keep map labels, blue points, daily tables, prose, and photo priority lists synchronized. Removing or moving a stop requires auditing every representation.
- Route lines are structural schematics through explicit control points, not turn-by-turn navigation. Do not present an approximate coordinate as an exact entrance, parking lot, or legal takeoff location.
- Use the locally bundled map fonts. Rebuild the WebP font subsets when new Chinese characters are introduced in reader-facing QMD files or `_quarto.yml`, and verify complete glyph coverage.
- Preserve WebP delivery, lazy loading, asynchronous decoding, and compact dimensions unless a measured quality or performance problem justifies a change.
- Drone recommendations must be conditional on current airspace, protected-area, border, weather, crowd, and onsite rules. Never describe an unverified takeoff point as permitted.

## 7. Research and evidence

- Treat weather forecasts, foliage timing, road closures, construction, park transport, opening hours, border access, fire-control rules, and drone restrictions as time-sensitive. Re-verify them when the answer or change depends on current conditions.
- Prefer official transport, government, scenic-area, meteorological, forestry, and aviation sources for rules and status. Use domestic travel platforms and social posts for recent visitor experience, congestion, viewpoints, and practical friction, not as sole authority for legal access.
- Record the publication or update date of time-sensitive evidence and distinguish current notice, seasonal norm, forecast, visitor report, and inference.
- Preserve disagreements and uncertainty. Do not silently choose the source that best supports a preferred route.
- Keep `sources.qmd` useful to travelers: link to the relevant current verification entry and express the operational decision it affects.
- If a referenced Xiaohongshu or other dynamic page cannot be read, do not invent its contents. Use an accessible copy, another source, or state the limitation.

## 8. Change discipline

- Inspect affected QMD pages, `data/itinerary.json`, generated maps, navigation, styles, workflow configuration, and directly related documentation before editing.
- Preserve unrelated user changes and current worktree state. Do not discard or overwrite work outside the requested scope.
- Fix the source of truth first. Do not patch generated HTML or map images to hide source-data inconsistency.
- Use `apply_patch` for source-file edits. Use project scripts for generated maps and standard formatters or generators for bulk binary outputs.
- Add or replace a dependency only when its value, compatibility, policy impact, and maintenance cost are justified; keep `requirements.txt` consistent.
- Do not add speculative fallbacks, stale alternatives, duplicate route files, temporary screenshots, or one-off reports to the repository.

## 9. Verification

Translate the requested outcome into observable checks and run those relevant to the change:

- parse `data/itinerary.json` and verify every route point, label, photo point, route kind, and context reference exists
- verify daily endpoint-to-next-start continuity for all affected plans
- audit repeated undirected route segments and classify each as required access/return travel or unintended repetition
- audit duplicate mapped photography points across days
- regenerate every affected map with `scripts/build_maps.py` and visually inspect labels, legends, route colors, blue points, and context insets
- render the Quarto site outside the tracked tree when practical
- check generated HTML pages, local assets, cross-page links, and fragment anchors
- inspect affected pages at desktop and mobile widths when layout, navigation, tables, maps, fonts, or styles change
- verify the subsetted web fonts cover every non-ASCII character used by QMD files and `_quarto.yml`
- run `git diff --check`, inspect `git status`, and review the final diff for accidental files, secrets, generated drift, and unrelated changes

Never claim a check passed when it was not run. State skipped or blocked validation and the resulting risk.

## 10. Publishing and external services

- Do not push, deploy, change cloud configuration, authorize an application, or create credentials unless the user requests or has already authorized that external action.
- When publishing is in scope, commit only intended files, push `main`, wait for `Publish Quarto roadbook`, and verify the public pages and changed assets after deployment.
- GitHub Pages publishes `gh-pages`; EdgeOne Pages should consume that prebuilt branch with root and output directory `./`. Do not make EdgeOne rebuild the Quarto sources unless the deployment architecture is intentionally changed.
- Use minimum GitHub App scope for EdgeOne: authorize only `aliosvictor/dongbei-roadbook` when possible.
- Never request or expose passwords, one-time codes, API tokens, or repository secrets in chat or committed files.

## 11. Completion and commit gate

Before claiming completion, and before any commit when committing is in scope, confirm that:

- the requested outcome and applicable success criteria are satisfied
- relevant verification passed or limitations are explicitly reported
- QMD prose, route schema, generated maps, navigation, source links, and deployment configuration agree
- both plans affected by a shared fact have been audited
- time-sensitive claims are current enough for their use and uncertainty is explicit
- no conflict markers, partial merges, stale temporary files, accidental outputs, duplicate artifacts, or secrets remain
- the final report states what changed, what was verified, what was skipped, and any material remaining risk
