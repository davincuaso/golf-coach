import { proxyAnalysis } from "@/lib/server/analysis-proxy";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 60;
export async function POST(request: Request): Promise<Response> {
  return proxyAnalysis(request, process.env, fetch, "session");
}
