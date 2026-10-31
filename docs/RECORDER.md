# Recorder and saved image conversion

The recorder records only acknowledged controls sent through Studio previews and Home/Back, bound to one device identity and connection generation. It does not observe external phone touches. Simulation uses the same recorder and normal spawned-worker replay. Start, pause/resume and stop recording from the Recorder workspace; pause/reset/disconnect/stop invalidate pending recording tickets. A failed or uncertain command stops recording rather than inventing a completed step.

The timeline exposes an action icon/type, editable Python call or delay, duration, device/image reference and selected-step screenshot properties. Insert an explicit delay, edit code, move entire rows up/down or delete them. Evidence follows the action during reorder/delete. Generate Python only after stopping. Code stays ordinary Python and is validated before insertion/save/replay. Drag/drop ordering and general arbitrary command insertion UI are deferred; edit a call or use Monaco.

## Convert a tap to an image

1. Leave **Capture pre-tap screenshots** enabled when recording. The screenshot is captured before sending a short coordinate tap; capture failure does not prevent input but leaves a clear no-evidence fallback.
2. Stop, select an explicit integer `tap(x, y)`, and choose **Convert to Image Target…**.
3. Inspect the associated **pre-tap** screenshot, draw a textured rectangle containing the original point, and save the actual PNG inside the current project's image library.
4. Only after save, containment/texture checks and verification that the timeline/project have not changed does the row become `click("images/target.png")`. Off-center taps produce a real `Pattern(...).targetOffset(dx, dy)` preserving the original tap position.
5. Insert Python or replay using the normal trusted worker. Reset the demo to the correct starting screen first. No automatic navigation/retry is added.

No screenshot, unsupported action, crop outside the point, constant image, external asset path or changed row/project means no replacement. A saved PNG may remain even when replacement is refused. You can create a target manually in Visual Tools and edit the generated Python instead. Conversion makes recognition-based code; it cannot guarantee the target's future uniqueness or stability.

## Sessions and safety

Save/open is explicit JSON data, never automatic execution. Schema 3 stores actions, duration metadata, original geometry, elapsed action timestamps and bounded base64 PNG evidence. Existing schema 1 and 2 sessions still load; timestamps are left absent when the original session did not contain them. Elapsed timestamps start at the first completed action and retain time spent paused; generated delays exclude paused time. Timestamps and screenshot evidence follow their action during reorder/delete and remain visible in the selected-step properties. Invalid timing stops recording without appending a successful action.

Limits: 2,000 steps, 4,096 characters per call, generated source ≤1 MiB, per screenshot ≤2 MB/8.5 MP, total screenshot evidence ≤6 MB, JSON ≤10 MB. Once the evidence budget is exhausted, further taps remain coordinate steps without convertible screenshots. Opening validates before replacing the current timeline. Full screenshots may contain private data: uncheck capture when unnecessary and review session files before sharing.

Replay verifies the selected idle target and captures its current geometry. A changed resolution warns explicitly; coordinates are not guessed/rescaled. Replay uses the same source approval, device lease, pause/stop and global emergency stop as scripts. Native Android input already sent cannot be undone. Reset/reconnection requires explicit restart and a new context; it never replays pending actions.
