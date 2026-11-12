export default function CaptureGuidePage() {
  return (
    <div className="panel evidence-workbench">
      <p className="eyebrow">A CLEARER VIEW</p>
      <h1>Capture useful evidence.</h1>
      <section className="evidence-section">
        <h2>One camera per swing</h2>
        <p>
          Keep each separate swing under a different Swing ID, even when you
          change angle within one practice session. Film with a stationary
          camera, enough light, the whole golfer visible, and the ball in frame.
          Preserve the original recording speed. More frames help only when the
          ball stays sharp and visible.
        </p>
        <p>
          For ball tracking, pause near impact and select the centre of the
          ball. Review every candidate point against the source. A lost ball
          ends the trace. An image-plane tracer alone does not measure spin,
          carry, or physical launch speed.
        </p>
        <p>
          The local detector is experimental. Its training did not specifically
          cover night footage; dark range videos may return insufficient
          evidence. No clips are sent to a model provider.
        </p>
      </section>
      <section className="evidence-section">
        <h2>Optional: calibrated 3D</h2>
        <p>
          Record the exact same swing simultaneously from two fixed cameras.
          Separate swings from different positions cannot form a calibrated 3D
          recording. Both cameras need matching lens calibration, a shared
          measured ground reference, and verified synchronization.
        </p>
        <ol className="evidence-notes">
          <li>
            Lock focus, zoom, orientation and resolution. Disable stabilization
            and reframing.
          </li>
          <li>
            Capture varied views of a measured checkerboard for each lens.
          </li>
          <li>
            Without moving the cameras, photograph the same level ground board
            from both cameras. Check identical physical corner labels, target
            direction, and scale.
          </li>
          <li>
            Use a shared timing signal with known uncertainty. Selecting
            similar-looking impact frames is not enough to establish 10 ms
            synchronization.
          </li>
          <li>
            Load both generated profiles in Sessions, enter timing anchors
            relative to the selected windows, and inspect reconstruction
            quality.
          </li>
        </ol>
      </section>
      <section className="evidence-section">
        <h2>Optional: shot readings</h2>
        <p>
          If you later have monitor readings, import CSV/JSON or enter values
          manually. Keep the units and measurement methods, match one shot to
          each Swing ID, and set your intended distance, direction and shape.
          Modelled carry remains labelled as modelled.
        </p>
      </section>
      <p className="help-text mt-5">
        Camera setup commands, model installation and data templates:{" "}
        <a
          className="text-button"
          href="https://github.com/davincuaso/golf-coach/blob/main/docs/calibration-and-shot-evidence.md"
          target="_blank"
          rel="noopener noreferrer"
        >
          Detailed setup guide
        </a>
        .{" "}
        <a
          className="text-button"
          href="https://huggingface.co/notjulietxd/golf-ball-tracker"
          target="_blank"
          rel="noopener noreferrer"
        >
          Detector model card
        </a>
        .
      </p>
    </div>
  );
}
