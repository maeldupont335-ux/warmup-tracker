import { NextRequest, NextResponse } from "next/server";
import { verifyCode, verify2FA } from "@/lib/telegram-client";
import { getDataDir } from "@/lib/data-dir";
import fs from "fs";
import path from "path";

export async function POST(req: NextRequest) {
  const { code, password } = await req.json();
  const hashFile = path.join(getDataDir(), "pending-hash.json");

  try {
    if (password) {
      // 2FA
      await verify2FA(password);
      return NextResponse.json({ ok: true });
    }

    if (!fs.existsSync(hashFile)) {
      return NextResponse.json({ error: "Session expirée, recommence" }, { status: 400 });
    }

    const { phoneCodeHash } = JSON.parse(fs.readFileSync(hashFile, "utf-8"));
    await verifyCode(code, phoneCodeHash);
    fs.unlinkSync(hashFile);
    return NextResponse.json({ ok: true });
  } catch (err: unknown) {
    const e = err as Error;
    if (e?.message === "2FA_REQUIRED") {
      return NextResponse.json({ requires2FA: true });
    }
    console.error(err);
    return NextResponse.json({ error: "Code incorrect" }, { status: 400 });
  }
}
