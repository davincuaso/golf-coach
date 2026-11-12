# Multi-video practice sessions

Open `/sessions` from the main navigation. Add recordings, choose a source window
around one swing, and set the camera view separately for each window. Click the
golfer's torso in the first frame of that window when bystanders are visible.
You can add another window from the same recording to analyze a later swing.

## Limits and storage

- Up to eight video windows per session, processed sequentially.
- Up to 250 MiB per source file by default, independently enforced by both servers.
- Up to 30 seconds of decoded video per analysis window, with bounded frame count,
  resolution, worker resources, and processing deadlines.

The 30-second limit protects analysis time and memory. It is not a bucket storage
quota. The upload byte limit protects transfer, temporary disk use, and request
size. Longer recordings can now be submitted with explicit start/end times; only
the selected window runs pose inference. Automatic discovery of every swing in a
long recording is not implemented.

The current implementation uploads the source file for each window and deletes
temporary backend media/results after processing. Selecting another window of
the same recording therefore uploads that source again. There is no upload-once
media cache or durable cloud session store. A configured Supabase object can also
be analyzed through the backend storage route, but the browser does not provision
or upload to a bucket. Hosting upload/deadline limits may be lower than app limits.

Keep the page open while processing. Completed reports survive a failed or
canceled window in the current page; Analyze session retries entries without a
result. Build / refresh session report combines completed entries into a partial
report when needed. Save session downloads the session and complete per-window
analysis JSON. Reloading or navigating away loses the in-memory session. The JSON
is an export for retention; importing it back into the workspace is not implemented.

Existing `.env` files are preserved by setup helpers. To adopt the new default,
set `GOLF_MAX_VIDEO_BYTES=262144000` in both backend and frontend server settings
and restart both services. Keep any deliberately lower hosting limit consistent.

## Separate swings and multiple views

Every entry starts with a distinct Swing ID. Use the **same** ID only for recordings
of the exact same physical swing, such as synchronized cameras. Different swings
from one practice session retain different IDs, even when the technique looks
similar. The application trusts this declaration; it does not verify synchronization.

Reviewed start/top/impact markers are relative to the selected window, not to the
original recording. The preview time buttons use that same local timebase. Pose
timestamps start at zero, while `pose.video.source_start_seconds` preserves the
actual first decoded source time for overlay alignment. Slow-motion exports need
their physical timebase checked before interpreting tempo.

The session preserves every clip's quality report, provisional measurements, and
coaching evidence. For reviewed statistics it:

1. Requires manually reviewed markers and metric-specific camera/tracking gates.
2. Chooses one supported source per metric and swing, ranked by torso coverage and
   gaps. Source IDs remain in the response; views never count as extra swings.
3. Withholds a metric when supported views disagree by more than 0.3 in tempo
   ratio or 5 degrees in posture loss. These are engineering review guards, not
   validated golf accuracy tolerances.
4. Reports medians/ranges and fault counts across distinct reviewed swings.

Automatic markers remain provisional and are excluded from reviewed statistics
and fault patterns. They still appear in the individual report and combined
ChatGPT prompt. Oblique/face-on footage can support reviewed timing; posture
screening requires the existing confirmed down-the-line view and tracking gates.
The app neither averages incompatible camera projections nor reconstructs 3D.
Linked views can be played side by side with independent controls.

Use consistent club and shot intent when interpreting a pooled session median.
The current session form does not collect those labels. A combined coaching prompt
contains all scalar/quality/rule evidence, source IDs, counts, conflicts, and partial
status. It is generated locally and sent to ChatGPT only when you copy/paste it.

## API contract

`POST /api/v1/analyses` and `/analyses/storage` accept these additional options:

```json
{
  "source_start_seconds": 40,
  "source_end_seconds": 46,
  "camera_view": "oblique",
  "events": { "start_seconds": 1, "top_seconds": 2, "impact_seconds": 2.3 }
}
```

The selected span must be positive and at most 30 seconds. A nonzero start
requires an explicit end. Without a window, the original whole-clip limit applies.
Each successful analysis also returns a `summary_token`: a signed compact copy of
server-computed scalar metrics/rules. It contains no media or server secret, but
it contains private measurements and is authenticated rather than encrypted.

`POST /api/v1/sessions` accepts JSON with backend bearer authentication:

```json
{
  "attempted_clips": 2,
  "clips": [
    { "clip_id": "view-a", "swing_id": "Swing 1", "summary_token": "<first report token>" },
    { "clip_id": "view-b", "swing_id": "Swing 1", "summary_token": "<second report token>" }
  ]
}
```

The endpoint verifies the report signatures, rejects duplicate analysis IDs, and
never trusts client-supplied metric values. Its body limit is 1 MiB. Tokens expire
after 24 hours and become invalid when the backend bearer secret rotates; reanalyze
an expired report to combine it again. Use Clear this result to reanalyze for that
entry, then Analyze session. Existing downloaded reports remain readable.

The response contains `session_id`, `status`, attempted/analyzed counts, distinct
swing groups with per-metric source IDs and conflicts, `tempo`/`posture_loss`
statistics, recurring `patterns`, `notices`, and one `prompt_payload`. There is no
server session database or retrieval endpoint. The frontend's same-origin
`/api/v1/sessions` proxy applies workspace authentication and keeps bearer auth on
the server.

## Next stages

Add automatic swing segmentation and explicit synchronization/calibration tools,
then validate against labelled golf footage. Dedicated visible-ball tracking and
launch-monitor CSV/JSON import remain the next evidence paths; current sessions
do not measure ball flight, carry, spin, or clubhead speed. See the
[accuracy and ball-flight plan](accuracy-and-ball-flight.md).
