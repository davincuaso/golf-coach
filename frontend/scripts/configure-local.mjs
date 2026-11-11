import { readFile, open } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const frontend = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
let backend;
try {
  backend = await readFile(path.join(frontend, "../backend/.env"), "utf8");
} catch {
  console.error(
    "Initialize backend/.env first: python backend/scripts/init_env.py",
  );
  process.exit(1);
}
const token = backend.match(
  /^GOLF_API_TOKEN=([A-Za-z0-9_-]{24,512})\s*$/m,
)?.[1];
if (!token || token.startsWith("replace-with")) {
  console.error(
    "Set a valid backend server token before linking the frontend.",
  );
  process.exit(1);
}
try {
  const handle = await open(path.join(frontend, ".env.local"), "wx", 0o600);
  try {
    await handle.writeFile(
      `GOLF_BACKEND_URL=http://127.0.0.1:8000\nGOLF_API_TOKEN=${token}\n`,
    );
  } finally {
    await handle.close();
  }
  console.log(
    "Created frontend/.env.local. The server token was not displayed.",
  );
} catch (error) {
  if (error?.code === "EEXIST")
    console.log("frontend/.env.local already exists; preserved its settings.");
  else {
    console.error("Could not create the local frontend settings.");
    process.exitCode = 1;
  }
}
