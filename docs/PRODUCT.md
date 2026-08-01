# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Static HTML/CSS/JavaScript rendered inside Electron.

## Users

Primary users are people who dictate text while working at a computer and need the result transcribed and pasted into the app they are using. This is inferred from the global shortcut, tray behavior, and transcription workflow.

## Product Purpose

AudioScribe captures spoken input, transcribes it through a configured provider, and sends the resulting text back into the user's workflow. Success means starting a dictation quickly, understanding its state, and getting usable text with minimal interruption.

## Positioning

The product's meaningful mechanism is always-available desktop dictation with a global shortcut and a lightweight floating status overlay. This is inferred from the Electron main process and overlay implementation.

## Operating Context

Users work in another desktop application while AudioScribe runs in the tray. The main window is used to configure the provider, microphone, shortcut, post-processing profiles, and diagnostics. The floating overlay communicates recording and transcription state without taking focus.

## Capabilities and Constraints

- Preserve the existing recording, transcription history, provider settings, microphone selection, global shortcut, profile, and pre-flight diagnostic flows.
- Preserve the Electron preload/API contract and the IDs consumed by `electron/ui/app.js`.
- The renderer currently uses localStorage for UI preferences and communicates with the main process through `window.api`.
- The interface currently mixes English labels with Portuguese runtime messages; the redesign may normalize visible copy without changing engine behavior.

## Brand Commitments

The product name AudioScribe is established. The user explicitly requests a clean, minimalist, modern interface with no AI-slop visual cues. No other visual brand commitment is confirmed.

## Evidence on Hand

The existing Electron renderer in `electron/ui/`, the global recording overlay, and the tray-driven workflow are the available product evidence. No customer, performance, or commercial claims were supplied; do not fabricate them.

## Product Principles

- The recording state must be understood at a glance.
- The global shortcut should remain the fastest path to action.
- Configuration should feel calm and reversible.
- System feedback should be specific, nearby, and non-dramatic.
- The interface should stay visually quiet while the user is working elsewhere.

