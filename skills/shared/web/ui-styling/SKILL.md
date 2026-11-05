---
name: ui-styling
description: Build beautiful, accessible UIs with shadcn/ui + Tailwind.
license: MIT
metadata:
  author: claudekit
  version: "1.0.0"
---

# UI Styling Skill

Create beautiful, accessible user interfaces with shadcn/ui components (built on Radix UI + Tailwind), Tailwind CSS utility-first styling, and canvas-based visual designs. Use when building user interfaces, implementing design systems, creating responsive layouts, adding accessible components (dialogs, dropdowns, forms, tables), customizing themes and colors, implementing dark mode, or establishing consistent styling patterns.

## Reference

- shadcn/ui: https://ui.shadcn.com/llms.txt
- Tailwind CSS: https://tailwindcss.com/docs

## When to Use This Skill

Use when building UI with React-based frameworks (Next.js, Vite, Remix, Astro), implementing accessible components, styling with utility-first CSS, creating responsive mobile-first layouts, implementing dark mode and theme customization, building design systems with consistent tokens, rapid prototyping, or adding complex UI patterns (data tables, charts, command palettes).

## Core Stack

### Component Layer: shadcn/ui
- Pre-built accessible components via Radix UI primitives
- Copy-paste distribution model (components live in your codebase)
- TypeScript-first with full type safety
- Composable primitives for complex UIs

### Styling Layer: Tailwind CSS
- Utility-first CSS framework
- Build-time processing with zero runtime overhead
- Mobile-first responsive design
- Consistent design tokens (colors, spacing, typography)
- Automatic dead code elimination

## Principles

- Accessibility first: semantic HTML, ARIA where needed, keyboard navigable, visible focus, WCAG AA contrast.
- Consistent tokens: a small set of color/spacing/typography tokens, applied everywhere; no one-off values.
- Proportional sizing: relative units (%, rem, fr) over fixed px for layout.
- Restraint: minimal styling that serves the content; no decoration for its own sake.
