import { NextRequest } from "next/server";
import { loadConfig, saveConfig } from "@/lib/config-store";

export const dynamic = "force-dynamic";

// Autorise app.only-chat.ai à pousser un token directement depuis la page (évite de faire
// transiter le token par un copier-coller manuel). Uniquement utile en local, sans risque
// puisque le serveur n'écoute que sur localhost.
const ALLOWED_ORIGIN = "https://app.only-chat.ai";

function withCors(res: Response) {
  res.headers.set("Access-Control-Allow-Origin", ALLOWED_ORIGIN);
  res.headers.set("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  res.headers.set("Access-Control-Allow-Headers", "Content-Type");
  return res;
}

export async function OPTIONS() {
  return withCors(new Response(null, { status: 204 }));
}

export async function GET() {
  const config = loadConfig();
  return withCors(
    Response.json({
      hasToken: !!config.accessToken,
      organizationId: config.organizationId,
      tokenSavedAt: config.tokenSavedAt,
    })
  );
}

export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => ({}));
  const { accessToken, refreshToken, organizationId } = body as {
    accessToken?: string;
    refreshToken?: string;
    organizationId?: string;
  };

  if (!accessToken || !organizationId) {
    return withCors(Response.json({ error: "accessToken et organizationId requis" }, { status: 400 }));
  }

  const saved = saveConfig({ accessToken, refreshToken: refreshToken ?? null, organizationId });
  return withCors(
    Response.json({ hasToken: !!saved.accessToken, organizationId: saved.organizationId, tokenSavedAt: saved.tokenSavedAt })
  );
}
