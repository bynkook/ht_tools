# Patch Application Instructions

This document describes how to apply the `@kanaries+graphic-walker+0.5.0.patch` file
to a fresh `node_modules` installation on a server or new development machine.

---

## Prerequisites

The patch file must be present in the `frontend/patches/` directory:
```
frontend/
  patches/
    @kanaries+graphic-walker+0.5.0.patch   ← required
    GW_PATCH_NOTES.md                      ← patch documentation
    PATCH_INSTRUCTIONS.md                  ← this file
```

---

## Step 1: Copy the Patch File

Copy `@kanaries+graphic-walker+0.5.0.patch` into the `frontend/patches/` directory on the target machine.

```bash
# Verify the file is in place
ls django_dev/frontend/patches/
# @kanaries+graphic-walker+0.5.0.patch should be listed
```

---

## Step 2: Run npm install

```bash
cd django_dev/frontend
npm install
```

The `postinstall` script in `package.json` automatically runs `patch-package`,
which applies all patches in the `patches/` directory immediately after `npm install` completes.

---

## Step 3: Verify postinstall Script

Confirm `package.json` has the following entry (required for automatic patching):

```bash
grep postinstall package.json
```

Expected output:
```json
"postinstall": "patch-package"
```

If missing, add it manually and re-run `npm install`.

---

## Step 4: Confirm Patch Was Applied

Check the `npm install` output for the following success message:
```
patch-package 8.x.x
Applying patches...
@kanaries/graphic-walker@0.5.0 ✔
```

To re-apply manually without running full `npm install`:
```bash
cd django_dev/frontend
npx patch-package
```

---

## Step 5: Verify Patch Contents

Run these checks to confirm each fix was applied correctly:

```bash
# Fix 1 — CSV UTF-8 BOM
grep -n "uFEFF" node_modules/@kanaries/graphic-walker/dist/graphic-walker.es.js

# Fix 2 — Unicode SQL Lexer
grep -n "UNICODE_ID_CHARS" node_modules/@kanaries/graphic-walker/dist/graphic-walker.es.js

# Fix 3 — CSV row sort
grep -n "analyticType.*dimension" node_modules/@kanaries/graphic-walker/dist/graphic-walker.es.js

# Fix 4 — Unicode field highlight
grep -n "p{L}.*p{N}" node_modules/@kanaries/graphic-walker/dist/graphic-walker.es.js
```

Each command should return **at least one result**. If any command returns nothing,
the corresponding fix was not applied.

---

## Troubleshooting

| Symptom | Cause | Solution |
|---------|-------|----------|
| `Hunk #N FAILED` during patch | Package version mismatch | Confirm version: `cat node_modules/@kanaries/graphic-walker/package.json \| grep '"version"'` — must be `0.5.0` |
| Patch re-applied but fixes disappear | `npx patch-package @kanaries/graphic-walker` was run, regenerating the patch from the (unpatched) node_modules | **Never run** `npx patch-package @kanaries/graphic-walker` unless intentionally regenerating. Always edit `node_modules` first, then regenerate. |
| `patch-package: command not found` | `patch-package` not installed | Run `npm install patch-package --save-dev` then retry |
| Patch not applied after `npm install` | Missing `postinstall` script | Add `"postinstall": "patch-package"` to `package.json` scripts |

---

## Important: Patch Regeneration Rule

> ⚠️ **Never run `npx patch-package @kanaries/graphic-walker` unless you intend to regenerate the patch.**

This command **overwrites** the patch file with a diff of the current `node_modules` state.
If the fixes are not already applied to `node_modules`, running this command will **erase** them from the patch file.

**Correct workflow for adding a new fix:**
1. Apply the change directly to `node_modules/@kanaries/graphic-walker/dist/graphic-walker.es.js`
2. Run `npx patch-package @kanaries/graphic-walker` to regenerate the patch file
3. Update `GW_PATCH_NOTES.md` to document the new fix

---

*Last updated: 2026-03-01*
