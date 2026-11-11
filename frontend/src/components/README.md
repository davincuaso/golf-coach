# Frontend components

`SwingWorkspace.tsx` owns the selected clip, analysis response and playhead.
`capture/` handles validated uploads, camera recording and cancelable analysis.
`analysis/` renders timestamp-aligned pose overlays, metrics, charts, rule feedback,
and `AiCoachingPrompt.tsx` with clipboard and external ChatGPT controls.
`AppShell.tsx` provides navigation. `LegacySettingsCleanup.tsx` only deletes the
retired localStorage object; it never reads or stores a credential.

See [the frontend guide](../../../docs/phase-4-frontend.md).
