import { NextRequest, NextResponse } from "next/server";
import { createServerClient } from "@supabase/ssr";

export async function middleware(req: NextRequest) {
  const res = NextResponse.next();
  const path = req.nextUrl.pathname;

  // Si les variables Supabase ne sont pas configurées, on laisse passer
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const supabaseKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!supabaseUrl || !supabaseKey) return res;

  let user = null;
  try {
    const supabase = createServerClient(supabaseUrl, supabaseKey, {
      cookies: {
        getAll() { return req.cookies.getAll(); },
        setAll(toSet) {
          toSet.forEach(({ name, value, options }) => res.cookies.set(name, value, options));
        },
      },
    });
    const { data } = await supabase.auth.getUser();
    user = data.user;
  } catch {
    // En cas d'erreur Supabase on laisse passer sans bloquer
    return res;
  }

  // Pages publiques
  if (path === "/" || path.startsWith("/login") || path.startsWith("/register")) {
    if (user && (path.startsWith("/login") || path.startsWith("/register"))) {
      return NextResponse.redirect(new URL("/dashboard", req.url));
    }
    return res;
  }

  // Dashboard + API protégés (sauf webhooks Telegram et fichiers médias)
  if (path.startsWith("/dashboard") || (
    path.startsWith("/api") &&
    !path.startsWith("/api/telegram/bot") &&
    !path.startsWith("/api/media/") &&
    !path.startsWith("/api/admin/")
  )) {
    if (!user) {
      return NextResponse.redirect(new URL("/login", req.url));
    }
  }

  return res;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.svg).*)"],
};
