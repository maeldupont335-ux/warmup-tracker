import { supabaseAdmin } from "./supabase";

export async function getOrCreateConversation(
  platform: string,
  fanId: string,
  fanUsername?: string,
  creatorName?: string
) {
  // Cherche conversation existante
  const { data: existing } = await supabaseAdmin
    .from("conversations")
    .select("*")
    .eq("platform", platform)
    .eq("fan_id", fanId)
    .single();

  if (existing) return existing;

  // Crée une nouvelle
  const { data: created, error } = await supabaseAdmin
    .from("conversations")
    .insert({ platform, fan_id: fanId, fan_username: fanUsername ?? null, creator_name: creatorName ?? null })
    .select()
    .single();

  if (error) throw error;
  return created;
}

export async function saveMessage(
  conversationId: string,
  role: "user" | "assistant",
  content: string,
  metadata?: Record<string, unknown>
) {
  const { error } = await supabaseAdmin.from("messages").insert({
    conversation_id: conversationId,
    role,
    content,
    metadata: metadata ?? {},
  });
  if (error) throw error;
}

export async function getHistory(conversationId: string, limit = 20) {
  const { data, error } = await supabaseAdmin
    .from("messages")
    .select("role, content")
    .eq("conversation_id", conversationId)
    .order("created_at", { ascending: true })
    .limit(limit);

  if (error) throw error;
  return (data ?? []) as { role: "user" | "assistant"; content: string }[];
}

export async function incrementDailyStats(field: "messages_sent" | "ppv_sold", revenue = 0) {
  const today = new Date().toISOString().split("T")[0];

  // Upsert stats du jour
  await supabaseAdmin.from("daily_stats").upsert(
    { date: today, [field]: 1, revenue },
    { onConflict: "date", ignoreDuplicates: false }
  );

  // Incrémente via RPC si disponible
  try {
    await supabaseAdmin.rpc("increment_stat", { p_date: today, p_field: field, p_revenue: revenue });
  } catch {
    // RPC optionnelle, pas bloquant
  }
}

export async function loadSettingsFromDB() {
  const { data } = await supabaseAdmin
    .from("ai_settings")
    .select("*")
    .eq("id", "00000000-0000-0000-0000-000000000001")
    .single();
  return data;
}

export async function saveSettingsToDB(settings: Record<string, unknown>) {
  await supabaseAdmin.from("ai_settings").upsert({
    id: "00000000-0000-0000-0000-000000000001",
    creator_name: settings.creatorName,
    personality: settings.personality,
    custom_prompt: settings.customPrompt,
    languages: settings.languages,
    ppv_enabled: settings.ppvEnabled,
    ppv_price: settings.ppvPrice,
    nudge_delay: settings.nudgeDelay,
    welcome_enabled: settings.welcomeEnabled,
    updated_at: new Date().toISOString(),
  });
}
