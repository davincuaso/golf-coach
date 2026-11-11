export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col justify-center gap-5 px-8">
      <p className="text-sm font-semibold uppercase tracking-widest text-emerald-700">Golf Coach</p>
      <h1 className="text-4xl font-semibold tracking-tight">Build a better swing.</h1>
      <p className="max-w-xl text-lg leading-relaxed">
        Project initialized. Offline pose analysis is available from the Python command line.
        Capture, comparison and coaching settings arrive in the next phases.
      </p>
    </main>
  );
}
