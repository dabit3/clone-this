# Parity Audit and Manifest Contract

## Discovery method

Treat the application as a graph of observable states and transitions.
A route is not a complete feature description.
A dialog, permission state, or failed request can expose another requirement on the same route.

1. Assign stable IDs to routes, features, journeys, and visual cases.
2. Add discovered branches to the frontier before exploring them.
3. Record edges as action, precondition, destination state, and side effect.
4. When implementation changes, preserve IDs.
5. Retain requirements that fail or become inaccessible.
6. Deduplicate equivalent data instances without collapsing distinct behavior.
7. Link each inventory item to source observations and acceptance tests.
8. Repeat the full audit after apparent completion.

A full sweep revisits every category and known branch.
A single homepage visit is not a sweep.
Two zero-discovery sweeps are a completion gate, not a guarantee about unavailable private systems.

## Mandatory audit categories

Use the following IDs in the manifest.
Record concrete evidence for each category, including categories that have no applicable feature.
For absent features, record where you searched and why the category has no further requirements.
Do not classify an inaccessible feature as absent.

### `source`: reference and source coverage

- Reference identity, version or capture time, entry points, and accessible scope.
- Available repository structure, route definitions, feature flags, schemas, tests, and API documentation.
- Documented features absent from the initial navigation.
- Public documentation, help pages, release information, and linked feature descriptions.
- Differences between source code, design files, documentation, and the running application.
- Authorized account roles and unavailable reference surfaces.
- A stable source snapshot or a record of reference changes during the run.

If the reference changes, invalidate affected evidence and discovery sweeps.
Use a consistent authorized reference version across the final suite.
If source code is unavailable, use runtime evidence without inventing implementation details.
If required behavior is inaccessible, add a blocker.

### `navigation`: routes and application structure

- Header, sidebar, footer, breadcrumbs, menus, nested menus, tabs, and contextual navigation.
- Public, authenticated, administrative, onboarding, and account routes where present.
- Deep links, route parameters, query parameters, hashes, redirects, and not-found routes.
- Back, forward, refresh, scroll restoration, and persisted navigation state.
- Dialogs, drawers, popovers, context menus, nested overlays, and dismissal rules.
- Sticky elements, overflow containers, infinite scroll, and mobile navigation.

### `roles`: authentication and access

- Sign-in, sign-out, registration, recovery, verification, and session expiry where present.
- Memberships, invitations, organizations, workspaces, role changes, and account switches.
- Anonymous, authenticated, restricted, administrator, and suspended states where observable.
- Route guards, server authorization, ownership checks, and direct API access restrictions.
- Feature availability by role, plan, permission, or account state.

Use local identities or explicitly authorized test accounts.
Do not use a clone to collect source credentials.
Do not bypass unavailable authentication steps.

### `states`: interactions and outcomes

- Every button, link, field, toggle, selector, tab, and keyboard shortcut.
- Form defaults, validation rules, dependent fields, limits, and submission behavior.
- Loading, skeleton, empty, success, error, disabled, read-only, and stale states.
- Search, filters, sorting, pagination, selection, bulk actions, and result counts.
- Drag-and-drop, reordering, resizing, clipboard actions, and context actions.
- Toasts, banners, confirmation dialogs, undo, retry, cancellation, and optimistic updates.
- Multi-step flows, saved drafts, interrupted actions, and duplicate submissions.

Verify each action through its actual result.
A notification alone does not prove data changed.

### `responsive`: visual states and layouts

- All observed layout families, breakpoints, themes, and density variants.
- Viewport width and height, device scale, orientation, and zoom behavior where supported.
- Typography, font loading, line breaks, letter spacing, baselines, and text overflow.
- Component geometry, padding, margins, grids, alignment, and content widths.
- Colors, borders, radii, shadows, gradients, opacity, and stacking order.
- Icons, imagery, cropping, aspect ratios, and image loading states.
- Hover, focus, active, selected, disabled, and expanded component states.
- Transitions, animation curves, timing, reduced motion, and scroll behavior.

If a web reference has no viewport measurements, start with these CSS viewport sizes:

| Layout | Width | Height |
| --- | ---: | ---: |
| Small phone | 375 | 812 |
| Large phone | 430 | 932 |
| Tablet | 768 | 1024 |
| Desktop | 1440 | 900 |
| Wide desktop | 1920 | 1080 |

These sizes are starting points, not limits.
Add the reference viewport and widths immediately before and after each discovered breakpoint.
Use the same viewport and pixel ratio for each reference/clone pair.

### `data`: persistence and integrations

- Data models, CRUD behavior, identifiers, relationships, and validation rules.
- Reload and restart persistence, concurrency, ordering, cache invalidation, and conflict behavior.
- Upload limits, accepted formats, previews, downloads, exports, and generated file contents.
- Import behavior, duplicate handling, progress indicators, and partial failure.
- Notifications, subscriptions, webhooks, synchronization, real-time updates, and background jobs.
- Billing, checkout, refunds, external providers, and plan enforcement where present.
- Timeout, retry, offline, expired authorization, and unavailable-provider behavior.

Use sandbox providers or isolated local services for state-changing verification.
A mocked provider does not prove a real integration works.
Keep unavailable integrations blocked until authorized end-to-end evidence exists.

### `assets`: assets and content

- Font families, exact weights, icon sets, logos, illustrations, and media.
- Labels, descriptions, helper text, placeholders, errors, and empty-state copy.
- Dates, currencies, numbers, timezones, translations, and text direction where present.
- Long text, missing images, special characters, large values, and minimum values.
- Asset provenance, licenses, attribution, and permitted reuse.

Use the actual authorized asset instead of a visual approximation.
If an essential asset is unavailable, record the resulting parity blocker.

### `accessibility`: semantic and input behavior

- Accessible names, labels, roles, heading structure, and landmark structure.
- Keyboard navigation, tab order, focus visibility, and focus restoration.
- Dialog focus traps, escape behavior, menu keys, and shortcut collisions.
- Live announcements, validation associations, and status messages.
- Touch targets, pointer interaction, zoom, text scaling, and reduced motion.

Preserve required semantics and safe accessibility behavior.
Record necessary deviations instead of silently claiming exact equivalence.

### `reliability`: release and failure behavior

- Clean installation, environment requirements, migrations, startup, and production build.
- Console errors, server errors, failed requests, and missing assets.
- Fresh-session flows, expired sessions, unavailable services, and recovery.
- Race conditions, rapid input, repeated actions, cancellation, and navigation during requests.
- Direct-route startup, saved state, cache state, and process restarts.
- Relevant performance behavior, responsiveness, and layout stability.

Do not treat a development server smoke test as production verification.

### `rebrand`: requested name replacement

- Product title, visible brand labels, document title, and application metadata.
- Manifest identity, package identity, local storage namespaces, and development service names where applicable.
- Existing attribution, license notices, provider names, and imported user content that must remain unchanged.
- Changed name width, line wrapping, alignment, and responsive behavior.
- Explicit visual normalization evidence for the requested name change.

Do not perform unrestricted search-and-replace across third-party content or API contracts.
Do not configure source production domains or endpoints as clone write targets.

## Functional test method

For each feature, define a test with:

1. A source observation and stable inventory ID.
2. Role, permissions, initial data, route, viewport, and environment.
3. A sequence of user actions.
4. Expected visible and persisted results.
5. Relevant error and boundary cases.
6. Reset steps within disposable, authorized fixtures.

Verify the source behavior before asserting the clone result.
Prefer semantic selectors and state-based waits over arbitrary delays.
Verify file contents, database effects, and network contracts where relevant.
Keep destructive fixture operations isolated from user and production data.

## Visual test method

1. Store original reference screenshots separately from clone screenshots.
2. Record capture environment, fixture identity, readiness conditions, and scroll position.
3. Repeat the source capture to identify genuine reference nondeterminism.
4. Stabilize the source and clone through the same permitted controls.
5. Compare corresponding screenshots at the same dimensions.
6. Save the raw pair, diff image, overlay, and machine-readable pixel metrics.
7. Even when a global similarity score appears high, inspect local differences.
8. Fix layout causes before adding component-specific offsets.
9. Re-run every affected visual case after shared styles change.

Exact mode requires zero differing pixels without masks or tolerance.
Normalized mode requires zero differing pixels after documented, narrowly bounded normalization.
Never use normalization to hide layout, content, or behavior that the clone does not implement.

For branding, prefer an authorized local reference with only the requested name substitution.
Otherwise, record the precise brand region and verify its new text, geometry, and behavior separately.
Report normalized comparisons explicitly in the final result.
If rendering environments cannot match, record the limitation rather than relaxing the gate silently.

## Manifest contract

Initialize the run with `../scripts/init_run.py`, which copies `../templates/state.json` into place.
The bundled scripts use Python 3.9 or newer and no third-party dependencies.
The manifest is a checkpoint and evidence index, not a substitute for application tests.

### Run directory

The run directory is `<clone_root>/.devin/clone-this/<safe-name>/`, and `state.json` sits at its top level.
All agents use this path, regardless of where they load the skill.
The `.devin` directory stores run data and does not require Devin CLI.
Do not rename it for another agent.
Keep the recorded clone root and run files in place when switching agents.

To derive `<safe-name>`, lowercase the name and replace each run of characters outside `a-z0-9` with `-`.
Remove leading and trailing `-`, keep at most 64 characters, then remove trailing `-` again.
If nothing remains, use `clone`.
The gate rejects a manifest whose directory is elsewhere or whose name does not derive from `clone_name`.

The initializer requires an existing clone root.
It reserves a new run directory without overwriting existing files.
It resumes only when `source`, `clone_name`, and `clone_root` exactly match the existing manifest.
It rejects unsupported schemas, missing event logs, and symlinked run paths.
If initialization stops partway through, preserve the partial directory for recovery instead of running a cleanup command.
Only one agent can write a run at a time.

### Top-level fields

| Field | Required value or meaning |
| --- | --- |
| `schema_version` | Integer `1` |
| `source` | Nonempty source project reference without secrets |
| `clone_name` | Nonempty requested product name |
| `clone_root` | Absolute path of an existing destination directory |
| `status` | `active`, `blocked`, `paused`, or `complete` |
| `iteration` | Nonnegative integer |
| `revision` | Output of `../scripts/fingerprint.py` for `clone_root` |
| `frontier` | Array of unexplored branches. Must be empty at completion. |
| `blockers` | Array of unresolved blockers. Must be empty at completion. |
| `unverified_assumptions` | Array of unresolved assumptions. Must be empty at completion. |
| `items` | Inventory records. Must cover all discovered requirements. |
| `audits` | One record for each mandatory audit ID |
| `checks` | One record for each mandatory check ID |
| `sweeps` | Ordered full-discovery sweep records |
| `next_action` | Concrete resume action, or the final delivery action |

### Fingerprint contract

The fingerprint covers included paths, contents, executable permission flags, and symlink targets.
It includes the listing method and an algorithm version marker.
The current algorithm uses `clone-this-fingerprint-v2` internally and prints `sha256:<digest>`.
Earlier hashes are stale even if the clone files did not change.
Recompute them and repeat final verification instead of relabeling old results.

Inside a Git repository, the script includes tracked files even when ignore rules match them.
It also includes untracked files that Git does not ignore.
It expands nested repositories and initialized submodules, including their uncommitted changes.
An unavailable submodule or Git error stops the calculation instead of silently changing the file set.

Outside a Git repository, the script walks the tree.
It skips the dependency, build, and cache directories listed in `WALK_EXCLUDED_DIRECTORIES` in `../scripts/fingerprint.py`.
It reports directory read errors instead of skipping unreadable files.
Both modes exclude `.devin/clone-this/` and desktop metadata files.
Neither mode follows source symlinks outside the clone root.
An included symlink to an excluded file or uncovered directory stops the calculation.

Before the final suite, inspect the file list and record its coverage in the reliability audit:

```sh
python3 -B "<actual-skill-directory>/scripts/fingerprint.py" "<clone-root>" --list
```

Make sure that source, tests, nonsecret configuration, lockfiles, and fixtures appear in the list.
Keep generated reports inside the run directory or existing generated-output exclusions.
Do not change exclusions to conceal relevant changes.
Record external service versions and nonsecret runtime parameters separately.
Do not copy secrets into the manifest or fingerprint report.

The gate recomputes the fingerprint from `clone_root` and rejects a different `revision`.
The fingerprint is not an atomic filesystem snapshot.
Stop writers before final verification, even though the script detects some concurrent file changes.
If the source reference, runtime parameters, or external fixtures change, invalidate affected evidence regardless of the clone fingerprint.

### Inventory records

Use these required fields:

```json
{
  "id": "feature-search",
  "kind": "feature",
  "label": "Search filters persisted records and preserves the query after reload",
  "status": "pending",
  "verified_revision": null,
  "evidence": []
}
```

Supported kinds are `route`, `feature`, `journey`, `visual`, `asset`, and `integration`.
At least one record of each first four kinds is required.
Add asset and integration records for every discovered requirement of those kinds.
Use `pending`, `in_progress`, `blocked`, or `verified` as the item status.
Only `verified` records satisfy the completion gate.

Keep detailed preconditions, source observations, test steps, and implementation locations in the linked evidence.
Additional manifest fields can also hold those details.
Preserve the required fields and stable IDs.

Every verified record requires the current `verified_revision` and a nonempty `evidence` array.
Each evidence path must identify a nonempty file inside the run directory.
Use relative paths with forward slashes.
Do not use absolute paths, parent traversal, or symlinks outside the run directory.

Each `visual` record also requires a `comparison` object:

```json
{
  "mode": "exact",
  "reference": "evidence/reference/search-desktop.png",
  "actual": "evidence/clone/search-desktop.png",
  "diff": "evidence/diffs/search-desktop.png",
  "different_pixels": 0,
  "total_pixels": 1296000
}
```

`reference` and `actual` must be PNG files with identical pixel dimensions.
`total_pixels` must equal the reference width multiplied by its height.
The gate reads the complete IHDR header, including its checksum and allowed dimensions, to enforce these rules.
Reference, actual, and diff paths must identify separate files, not aliases or hard links to the same file.
The gate does not decode pixel data or detect every form of image corruption.
The comparison tool must decode the full images and save its results.

For normalized mode, set `mode` to `normalized`.
Add `normalization_evidence` with a path to the normalization bounds, reason, method, and independent behavior results.
Keep the original screenshots in the evidence directory.
Link the harness output that produced the pixel counts through the item's `evidence` array.
The verifier does not calculate `different_pixels` or authenticate screenshot contents.

### Audits and checks

Use this shape for each audit:

```json
{
  "id": "navigation",
  "status": "pending",
  "verified_revision": null,
  "evidence": []
}
```

An audit passes only with `status: "verified"`, the current revision, and evidence.
Use all ten audit IDs defined in this document.

Checks use the same shape but require `status: "passed"` at completion:

| Check ID | Evidence required |
| --- | --- |
| `functional` | End-to-end journeys and applicable unit, integration, persistence, and provider results |
| `visual` | Full visual matrix, raw captures, diffs, metrics, and normalization disclosures |
| `build` | Clean installation and production build or native release results |
| `quality` | Project-required lint, type, accessibility, and runtime diagnostics |
| `security` | Authorization, secret exposure, dependency, and unsafe-side-effect review results |

Do not mark an unavailable command as passed.
If an equivalent command verifies the same property, use that command instead.
Record nonapplicable subchecks with evidence rather than inventing a successful command.

### Sweep records

Append one record after each complete discovery sweep:

```json
{
  "revision": "<current-content-fingerprint>",
  "new_items": 0,
  "frontier_empty": true,
  "audit_ids": [
    "source", "navigation", "roles", "states", "responsive",
    "data", "assets", "accessibility", "reliability", "rebrand"
  ],
  "evidence": ["evidence/discovery/sweep-002.json"]
}
```

Both final sweeps must cover every audit ID and share the current revision.
Each sweep needs its own evidence file from an actual repeat inspection.
If a sweep finds another requirement, reset the zero-discovery sequence and return to implementation.
Do not fabricate a sweep by copying an earlier record or renaming its evidence.

### Iteration log

`events.jsonl` sits beside `state.json` and holds one JSON object per line in UTF-8 text.
It follows the same path containment rules as other evidence files.
The gate reads it line by line and reports the original line numbers for invalid records.
After each iteration, append an event with the revision, changed IDs, commands, outcomes, blockers, and next action:

```json
{"iteration": 12, "revision": "<current-content-fingerprint>", "changed": ["feature-search"], "commands": ["npx playwright test search"], "outcome": "Search filters persist after reload.", "blockers": [], "next_action": "Capture the mobile search layout."}
```

Every record requires a nonempty `revision`; the other fields are the recommended shape.
Keep command output references instead of secret-bearing command arguments.
The verifier requires the log to exist, parses every line, and requires the final record to carry the current revision.
Never rewrite earlier records.

## Resume and blocker protocol

If the session resumes:

1. Read the manifest and recent events.
2. Recompute the content fingerprint with `../scripts/fingerprint.py` and compare it with `revision`.
3. Inspect services, fixtures, and the reference for changes.
4. Invalidate stale evidence.
5. Continue the recorded next action or the highest-impact unresolved requirement.

If a blocker remains:

1. Record the affected IDs and the missing access, tool, asset, or external capability.
2. Record attempted safe alternatives and their results.
3. Request required access or approval without asking unrelated product questions.
4. Continue other actionable work.
5. If no safe action remains, preserve a blocked checkpoint and report the exact resume condition.

Do not reduce scope or mark an item verified to bypass a blocker.
A blocked checkpoint is an incomplete run, not a successful clone.
