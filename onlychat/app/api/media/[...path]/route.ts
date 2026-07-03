import { NextRequest, NextResponse } from "next/server";
import { getDataDir } from "@/lib/data-dir";
import fs from "fs";
import path from "path";

const MIME: Record<string, string> = {
  jpg: "image/jpeg", jpeg: "image/jpeg", png: "image/png",
  gif: "image/gif", webp: "image/webp", heic: "image/heic",
  mp4: "video/mp4", mov: "video/quicktime", webm: "video/webm",
  avi: "video/x-msvideo", mkv: "video/x-matroska",
};

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path: segments } = await params;
  // segments = [userId, creatorId, folder, filename]
  const filePath = path.join(getDataDir(), "uploads", ...segments);

  // Sécurité : empêche la traversée de répertoire
  const uploadsRoot = path.join(getDataDir(), "uploads");
  if (!filePath.startsWith(uploadsRoot)) {
    return new NextResponse("Forbidden", { status: 403 });
  }

  if (!fs.existsSync(filePath)) {
    return new NextResponse("Not found", { status: 404 });
  }

  const ext = filePath.split(".").pop()?.toLowerCase() ?? "";
  const mime = MIME[ext] ?? "application/octet-stream";
  const buffer = fs.readFileSync(filePath);

  return new NextResponse(buffer, {
    headers: {
      "Content-Type": mime,
      "Cache-Control": "public, max-age=31536000, immutable",
    },
  });
}
