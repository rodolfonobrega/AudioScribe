# AudioScribe interface

## Direction

AudioScribe is treated as a quiet desktop operations desk: the interface makes recording state, the next action, and recent output legible without looking like an AI dashboard. The visual carrier is a broadcast cue sheet translated into a restrained Electron utility.

## Visual language

- Dark mode is the primary scene: charcoal surfaces, warm off-white text, thin graphite rules, and one muted amber signal for active or actionable states.
- Light mode inverts the same system into warm off-white paper and ink, preserving the restrained amber accent.
- Components are mostly flat and rectangular. Depth comes from spacing and grouped rules, not glass, gradients, decorative glow, or floating card stacks.
- Typography uses the native system sans stack for a platform-appropriate, quiet desktop feel. Monospace is reserved for shortcuts, latency, and small operational identifiers.
- Icons are inline SVG line icons with text labels; emoji are not part of the interface system.

## Layout

- A fixed-width left rail provides the four work areas: Gravar, Perfis, Configuração, and Diagnóstico.
- The main workspace uses a narrow reading measure and generous vertical rhythm.
- The recording view gives the primary task the first visual weight: status, one recording action, shortcut, then recent transcriptions.
- Metrics are secondary and compact. They never compete with the recording control.

## Interaction rules

- Use the amber accent for active navigation, recording focus, shortcuts, and operational signals.
- Keep state transitions short and functional. Respect `prefers-reduced-motion`.
- Preserve visible keyboard focus and use at least 44px targets for primary controls where possible.
- Error states are plain-language, local to the affected area, and paired with a direct repair action.

## Scope

The current visual world covers `electron/ui/index.html`, `style.css`, `app.js`, `overlay.html`, and `overlay.css`. Engine behavior, preload contracts, global shortcut behavior, and localStorage keys remain outside the visual system and were preserved.
