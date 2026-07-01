import { NextRequest, NextResponse } from "next/server";
import { loadAppConfig, saveAppConfig, getWebhookBase } from "@/lib/app-config";

export async function GET() {
  const cfg = loadAppConfig();
  return NextResponse.json({ ...cfg, resolvedUrl: getWebhookBase() });
}

export async function POST(req: NextRequest) {
  const body = await req.json();
  const cfg = loadAppConfig();
  if (body.productionUrl !== undefined) {
    cfg.productionUrl = body.productionUrl.trim().replace(/\/$/, "");
  }
  saveAppConfig(cfg);
  return NextResponse.json({ ok: true, resolvedUrl: getWebhookBase() });
}
