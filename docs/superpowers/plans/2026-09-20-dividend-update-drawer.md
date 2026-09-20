# Dividend Update Drawer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move dividend-data maintenance controls into a right-side drawer while preserving every existing update request and scheduler configuration flow.

**Architecture:** Extract a presentational `DataUpdateDrawer` component that receives the page's existing update callbacks and state. `page.tsx` remains the owner of API hooks, refresh keys, report output, and scheduler-modal state; it replaces the scattered toolbar controls with one stable-width entry button.

**Tech Stack:** Next.js 15, React 19, TypeScript, Tailwind CSS 4, Playwright.

---

### Task 1: Describe the drawer entry-point behavior with an end-to-end test

**Files:**
- Create: `apps/dividend/e2e/data-update-drawer.spec.ts`
- Modify: `apps/dividend/package.json`

- [ ] **Step 1: Write the failing Playwright test**

```ts
import { expect, test } from '@playwright/test';

test('opens data update drawer and exposes scheduler settings', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: /数据更新/ }).click();
  await expect(page.getByRole('complementary', { name: '数据更新' })).toBeVisible();
  await expect(page.getByRole('button', { name: '自动更新设置' })).toBeVisible();
});
```

- [ ] **Step 2: Run the test and verify it fails because the entry point does not exist**

Run: `pnpm exec playwright test e2e/data-update-drawer.spec.ts`

Expected: FAIL locating the `数据更新` button.

- [ ] **Step 3: Add a `test:e2e` package script only if Playwright is present in the installed dependencies**

```json
"test:e2e": "playwright test"
```

### Task 2: Extract the data-maintenance controls into an accessible right-side drawer

**Files:**
- Create: `apps/dividend/src/components/DataUpdateDrawer.tsx`
- Modify: `apps/dividend/src/app/page.tsx`

- [ ] **Step 1: Implement a controlled `DataUpdateDrawer`**

The component must render only while `isOpen`, use `role="complementary" aria-label="数据更新"`, close on overlay click or Escape, and leave body scrolling enabled. It receives existing update statuses and callbacks as props; it must not call APIs itself.

- [ ] **Step 2: Move existing update interactions without changing their behavior**

Preserve the existing dividend update, index status/retry, auxiliary-data rows (including force flags and bulk update), M120 update, realtime update, and status text. Replace the current toolbar controls with one `数据更新` button whose badge is the count of pending auxiliary updates plus pending dividend/M120 updates.

- [ ] **Step 3: Move scheduler entry into the drawer**

Use the existing `setSchedulerOpen(true)` callback for an `自动更新设置` button at the drawer bottom. Keep `SchedulerSettingsModal` unchanged.

- [ ] **Step 4: Run the E2E test and verify it passes**

Run: `pnpm exec playwright test e2e/data-update-drawer.spec.ts`

Expected: PASS.

### Task 3: Verify type safety and the production build

**Files:**
- Modify: `apps/dividend/src/components/DataUpdateDrawer.tsx`
- Modify: `apps/dividend/src/app/page.tsx`

- [ ] **Step 1: Run TypeScript validation**

Run: `pnpm exec tsc --noEmit`

Expected: exits 0.

- [ ] **Step 2: Build the app**

Run: `pnpm build`

Expected: Next.js production build completes successfully.

