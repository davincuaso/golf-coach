import Link from "next/link";
export default function NotFound() {
  return (
    <div className="panel error-panel">
      <p className="eyebrow">PAGE NOT FOUND</p>
      <h1>Back to your practice.</h1>
      <p>This page is not in your workspace.</p>
      <Link href="/" className="button button-primary">
        Return to Swing Lab
      </Link>
    </div>
  );
}
