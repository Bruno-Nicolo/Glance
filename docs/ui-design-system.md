# UI Design System

Glance UI uses shadcn/ui-style React components with Tailwind CSS v4.

## Theme

The base theme comes from tweakcn:

```text
https://tweakcn.com/r/themes/cmn03ysoc000104l23m768ey9
```

The theme is applied through `apps/ui/src/renderer/styles.css`. Keep shadcn theme tokens
there instead of scattering raw colors through React components.

## Component Rules

Use shadcn components from `apps/ui/src/components/ui/` for common controls:

- `Button` for commands and icon buttons
- `Card` for bounded panels
- `Badge` for compact status labels
- `Separator` for grouped panel sections
- `Switch` for boolean settings

Use `cn` from `apps/ui/src/lib/utils.ts` when composing component class names.

## Configuration

- shadcn config: `apps/ui/components.json`
- Tailwind Vite plugin and alias: `apps/ui/vite.renderer.config.ts`
- TypeScript alias: `apps/ui/tsconfig.json`
