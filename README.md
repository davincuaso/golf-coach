# Golf Coach

AI-assisted golf swing analysis using open-source pose estimation, coordinate
math, deterministic coaching rules, and optional Bring Your Own Key (BYOK)
OpenAI synthesis.

**Current status:** Phases 1–4 are implemented: pose processing, FastAPI, hybrid
coaching, and a functional Next.js 15 Swing Lab with capture and BYOK settings.
This is a single-tenant workspace. No cloud bucket is provisioned automatically;
direct-to-bucket uploads and a pro reference library remain future integrations.

## What is implemented

- YOLO COCO-17 pose extraction with confidence checks and single-subject tracking.
- Timestamp-aware Butterworth smoothing, bounded gap interpolation, and JSON export.
- 2D spine posture measurements, swing tempo, and labelled swing-event estimates.
- Rule-based posture/tempo observations with evidence and specific practice drills.
- Optional request-scoped OpenAI coaching with rule-only fallback.
- FastAPI video upload, private Supabase download, and existing-pose coaching routes.
- Bounded worker processes, upload limits, temporary cleanup, and backend tests.
- Camera recording, drag/drop upload, video playback and timestamp-aligned pose overlays.
- Kinematic charts, rule/AI feedback, drills, and credential-free JSON exports.
- Persistent browser BYOK preferences, optional AI synthesis, and a protected server proxy.

The backend uses Python, FastAPI, OpenCV, Ultralytics, NumPy, and SciPy. The
frontend uses Next.js 15, React 19, TypeScript, Tailwind CSS 4, and Zod.

For the server, configuration, API examples and verification, see
[Phase 3: FastAPI and hybrid coaching](docs/phase-3-api.md). For the web workspace,
settings lifecycle, deployment configuration, and file map, see
[Phase 4: frontend](docs/phase-4-frontend.md).

## Quick start

Use Python 3.12 and native Node.js 24. Clone the repository first:

```sh
git clone https://github.com/davincuaso/golf-coach.git
cd golf-coach
```

### Backend

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements-dev.txt
python backend/scripts/init_env.py
cd backend
python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --no-access-log
```

The setup helper creates an ignored `backend/.env` with a random backend bearer
token and preserves existing configuration. Configure an existing trusted pose
checkpoint before analyzing a video; see the model download instructions below.
Open the interactive API documentation at `http://127.0.0.1:8000/docs`.

### Frontend

In another terminal, from the repository root:

```sh
cd frontend
npm ci
npm run setup:local
npm test
npm run typecheck
npm run dev -- --hostname 127.0.0.1
```

Open `http://127.0.0.1:3000`. Upload or record a swing, choose its camera view,
and analyze. Use `/settings` to save an optional OpenAI key and enable synthesis.
The setup helper links the private backend token without exposing it in the browser.
Keep the backend running in the other terminal. For production, configure a workspace
password and public origin before `npm run build` / `npm start`; see the frontend guide.

Next.js 15 uses Webpack by default for these scripts.
No remote fonts are needed to build. Secrets, local videos, generated analyses,
model weights and dependencies are excluded by the root `.gitignore`.

The requested dependencies are pinned in `backend/requirements.txt`; exact
frontend resolution is recorded in `frontend/package-lock.json`. Python direct
pins are not a transitive, hash-verified deployment lock. Produce a target-specific
lock in the deployment environment before shipping the later phases.

MediaPipe is installed for a future alternative adapter, but this processor uses
only YOLO's COCO-17 output. Version 0.10.31 avoids installing a second distribution
that also owns `cv2`. Its upstream macOS wheel has an incorrect internal Linux
tag: imports succeed here, but `pip check` flags its platform metadata. Do not
treat a clean production dependency audit as completed; isolate this optional
adapter or replace its wheel when preparing deployment.

## Download trusted model weights once

From the project root with the Python environment activated:

```sh
export YOLO_CONFIG_DIR="$PWD/data/.ultralytics"
export MPLCONFIGDIR="$PWD/data/.matplotlib"
cd backend/models
python -c 'from ultralytics import YOLO; YOLO("yolov8x-pose.pt")'
cd ..
```

The x-size model favors accuracy over throughput; CPU processing can be slow.
Use `yolov8n-pose.pt` for a small development test. Only load trusted `.pt` files.
Offline processing requires an existing local file and never downloads a model.
Ultralytics licensing must be assessed before a commercial release:
[vendor licensing](https://www.ultralytics.com/license).

## Analyze a swing

Place a short, single-golfer video in the ignored `data/` directory. With your
working directory now `backend/`:

```sh
../.venv/bin/python -m app.vision.vision_processor \
  --input ../data/swing.mp4 \
  --output ../data/swing.analysis.json \
  --weights models/yolov8x-pose.pt \
  --device cpu \
  --cutoff-hz 8
```

For Apple Silicon use `--device mps` after testing model support, or `--device 0`
on a configured CUDA machine. When multiple people are visible, crop to the
golfer or supply `--subject-point 0.5 0.5` inside the golfer's initial bounding
box. The point uses normalized image coordinates. Existing results are protected;
pass `--overwrite` only when intentionally replacing one.

The output contains 17 named landmarks and nine 2D angles per frame, plus quality
flags, timestamps, a skeleton graph, configuration and model/file hashes. See
[the complete JSON contract](docs/vision-contract.md). No confident observation
means unknown coordinates/angles, not zeros. Butterworth filtering happens after
inference, uses timestamps, handles short gaps and leaves long occlusions unknown.

## Verification

From `backend/`:

```sh
../.venv/bin/python -m pytest -q
../.venv/bin/python scripts/smoke_pose.py
../.venv/bin/python scripts/smoke_api.py
```

The tests cover angle math, filtering, missing data, variable sampling, subject
selection, limits, real video decoding and atomic strict JSON output. The smoke
script explicitly downloads a small official model and runs actual YOLO inference
on a short video built from Ultralytics' bundled sample image. It checks wiring,
not golf-specific pose accuracy. A labelled golf dataset is still needed for that.

The API smoke test exercises authenticated uploads through a real isolated YOLO
worker. OpenAI and storage integrations are tested with mock transports; live
provider credentials are not included.

## Credentials, storage, and measurement limits

OpenAI keys arrive in the `X-OpenAI-API-Key` request header and are used by a
request-scoped client. They are not written to configuration, worker jobs, model
prompts, or results. A disabled or unavailable LLM leaves rule-based feedback
available. Server tokens and Supabase service credentials remain server-side.

The API is single tenant. The frontend streams uploads through a protected Next.js
server route. Backend/service tokens stay server-side. BYOK settings persist in
browser localStorage, which is readable by same-origin scripts and is not an
encrypted vault. Use a personal device and forget the saved key when finished.
Direct-to-bucket uploads and per-user storage ownership remain integration work.
Use HTTPS and deployment resource limits before exposing the service outside
localhost; see the Phase 3 and Phase 4 guides.

Angles are 2D camera projections. Automatic swing markers are labelled estimates,
and COCO-17 has no club landmarks. The application does not claim measured
clubhead speed, 3D biomechanics, or a definitive diagnosis from this footage.

Private videos, generated analyses, model weights, dependencies, build output,
and real `.env` files are excluded from version control. Download model weights
locally and supply your own provider/storage configuration.

## Source structure

Generated dependencies, caches and Next build output are omitted below.

```text
golf-coach/
├── .editorconfig
├── .gitignore
├── .nvmrc
├── .python-version
├── README.md
├── backend/
│   ├── .env.example
│   ├── pyproject.toml
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   ├── app/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── errors.py
│   │   ├── main.py
│   │   ├── storage.py
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── README.md
│   │   │   ├── middleware.py
│   │   │   └── routes.py
│   │   ├── coaching/
│   │   │   ├── __init__.py
│   │   │   ├── README.md
│   │   │   ├── kinematics.py
│   │   │   ├── rule_engine.py
│   │   │   ├── schemas.py
│   │   │   └── llm_synthesizer.py
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   └── analysis.py
│   │   └── vision/
│   │       ├── __init__.py
│   │       ├── vision_processor.py
│   │       └── worker.py
│   ├── models/README.md
│   ├── scripts/
│   │   ├── analyze.py
│   │   ├── init_env.py
│   │   ├── smoke_api.py
│   │   └── smoke_pose.py
│   └── tests/
│       ├── coaching_fixtures.py
│       ├── test_api.py
│       ├── test_coaching.py
│       ├── test_llm_synthesizer.py
│       ├── test_storage_and_worker.py
│       └── test_vision_processor.py
├── data/.gitkeep
├── docs/
│   ├── phase-3-api.md
│   ├── phase-4-frontend.md
│   └── vision-contract.md
└── frontend/
    ├── .env.example
    ├── eslint.config.mjs
    ├── next-env.d.ts
    ├── next.config.ts
    ├── package.json
    ├── package-lock.json
    ├── postcss.config.mjs
    ├── tsconfig.json
    ├── scripts/{configure-local,smoke-web}.mjs
    ├── tests/{settings,upload,proxy,visualization}.test.ts
    └── src/
        ├── app/
        │   ├── api/v1/analyses/route.ts
        │   ├── settings/page.tsx
        │   ├── globals.css
        │   ├── layout.tsx
        │   ├── page.tsx
        │   ├── error.tsx
        │   └── not-found.tsx
        ├── components/
        │   ├── AppShell.tsx
        │   ├── SwingWorkspace.tsx
        │   ├── capture/
        │   ├── analysis/
        │   └── ui/Icon.tsx
        ├── lib/
        │   ├── api-types.ts
        │   ├── analysis-client.ts
        │   ├── capture.ts
        │   ├── settings-storage.ts
        │   ├── visualization.ts
        │   ├── workspace-auth.ts
        │   └── server/analysis-proxy.ts
        ├── middleware.ts
        └── state/ApiKeyContext.tsx
```

The complete frontend file map and operating guide are in
[Phase 4](docs/phase-4-frontend.md). Run `npm test` and `npm run build` in
`frontend/` to verify the browser and server-boundary code. With both development
servers running and the backend smoke fixture prepared, `npm run smoke:web`
exercises the complete Next.js → FastAPI → isolated YOLO upload path.


References: [YOLO pose](https://docs.ultralytics.com/tasks/pose/),
[YOLOv8](https://docs.ultralytics.com/models/yolov8/),
[SciPy SOS filtering](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.sosfiltfilt.html),
[Next.js setup](https://nextjs.org/docs/app/getting-started/installation).
