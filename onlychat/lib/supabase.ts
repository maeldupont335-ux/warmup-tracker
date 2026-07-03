import { createClient } from "@supabase/supabase-js";

// Client côté serveur (service role — accès total, jamais exposé au browser)
export const supabaseAdmin = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.SUPABASE_SERVICE_ROLE_KEY!
);

// Client côté browser (anon key)
export const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
);

// Types
export interface Conversation {
  id: string;
  platform: "telegram" | "onlyfans" | "test";
  fan_id: string;
  fan_username: string | null;
  creator_name: string | null;
  created_at: string;
  updated_at: string;
  total_revenue: number;
}

export interface Message {
  id: string;
  conversation_id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
  metadata: Record<string, unknown> | null;
}
