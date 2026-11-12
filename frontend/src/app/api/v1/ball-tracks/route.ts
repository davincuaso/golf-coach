import { proxyAnalysis } from "@/lib/server/analysis-proxy";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 300;
export async function POST(request: Request) {
  return proxyAnalysis(request, process.env, fetch, "ball-track");
}
