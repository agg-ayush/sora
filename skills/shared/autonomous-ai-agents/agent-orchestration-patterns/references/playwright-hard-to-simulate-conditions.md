# Testing browser conditions that are hard to reproduce

Inspect existing test hooks and the real event-handling code before adding a synthetic trigger. Use Playwright's WebSocket routing or deliberate DOM state injection for a deterministic handler test; name exactly which browser-visible event/close mode is simulated. `WebSocketRoute.close()` closes one side; it does not guarantee byte-for-byte equivalence with a real upstream transport failure or OS/network loss.

For fullscreen/visibility/backgrounding, injected events can verify handler branches but do not prove the browser/OS will dispatch the same sequence or timing. Add a real-browser/manual check for platform-dependent behavior, and label what remains simulated. Restore injected state and event listeners after each test; assert the actual recovery UI/connection state rather than simply observing a callback invocation.
