export interface StyleProfile {
  // Exemples réels de tes messages (pour few-shot)
  realExamples: { fanMessage: string; yourReply: string }[];

  // Patterns extraits
  commonEmojis: string[];
  commonPhrases: string[];
  avgMessageLength: number;
  usesAbbreviations: boolean;
  commonGreetings: string[];
  commonSignoffs: string[];

  // Stats
  totalMessagesAnalyzed: number;
  yourName: string;
}

interface TelegramMessage {
  id: number;
  type: string;
  date: string;
  from?: string;
  from_id?: string;
  text: string | { type: string; text: string }[];
}

interface TelegramExport {
  name?: string;
  messages: TelegramMessage[];
}

function extractText(raw: TelegramMessage["text"]): string {
  if (typeof raw === "string") return raw;
  if (Array.isArray(raw)) return raw.map(p => (typeof p === "string" ? p : p.text ?? "")).join("");
  return "";
}

function extractEmojis(text: string): string[] {
  const emojiRegex = /\p{Emoji_Presentation}|\p{Extended_Pictographic}/gu;
  return [...new Set(text.match(emojiRegex) ?? [])];
}

function detectAbbreviations(texts: string[]): boolean {
  const abbrevPatterns = /\b(mdr|lol|ptdr|jsp|tfk|wsh|ngl|btw|omg|rip|bcp|pr|tt|tjrs|svp|stp|imo|irl|tmtc|bg|sk|kikou|cc|slt|bjr|bsr|bcp|jtm|je t'aime|bisous|bises|xo|bb|babe|cheri|chéri)\b/i;
  return texts.some(t => abbrevPatterns.test(t));
}

export function analyzeTelegramExport(
  exportData: TelegramExport,
  yourName: string
): StyleProfile {
  const messages = exportData.messages.filter(m => m.type === "message");

  // Sépare tes messages vs ceux des fans
  const yourMessages = messages.filter(m =>
    m.from && (m.from.toLowerCase().includes(yourName.toLowerCase()) || m.from === yourName)
  );
  const otherMessages = messages.filter(m =>
    m.from && !m.from.toLowerCase().includes(yourName.toLowerCase())
  );

  // Extraire le texte de tes messages
  const yourTexts = yourMessages
    .map(m => extractText(m.text))
    .filter(t => t.trim().length > 0 && t.trim().length < 300);

  // Construire des paires question/réponse (fan → toi)
  const pairs: { fanMessage: string; yourReply: string }[] = [];
  for (let i = 0; i < messages.length - 1; i++) {
    const current = messages[i];
    const next = messages[i + 1];
    const currentIsOther = current.from && !current.from.toLowerCase().includes(yourName.toLowerCase());
    const nextIsYou = next.from && next.from.toLowerCase().includes(yourName.toLowerCase());

    if (currentIsOther && nextIsYou) {
      const fanMsg = extractText(current.text).trim();
      const yourReply = extractText(next.text).trim();
      if (fanMsg.length > 2 && yourReply.length > 2 && yourReply.length < 200) {
        pairs.push({ fanMessage: fanMsg, yourReply });
      }
    }
  }

  // Sélectionne les 30 meilleurs exemples (variés)
  const selectedPairs = selectDiverseExamples(pairs, 30);

  // Emojis les plus utilisés
  const allEmojis = yourTexts.flatMap(t => extractEmojis(t));
  const emojiFreq: Record<string, number> = {};
  for (const e of allEmojis) emojiFreq[e] = (emojiFreq[e] ?? 0) + 1;
  const topEmojis = Object.entries(emojiFreq)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10)
    .map(([e]) => e);

  // Phrases courtes récurrentes (salutations, fins de message)
  const shortMessages = yourTexts.filter(t => t.split(" ").length <= 5);
  const phraseFreq: Record<string, number> = {};
  for (const p of shortMessages) {
    const clean = p.toLowerCase().trim();
    phraseFreq[clean] = (phraseFreq[clean] ?? 0) + 1;
  }
  const commonPhrases = Object.entries(phraseFreq)
    .filter(([, count]) => count >= 2)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 15)
    .map(([phrase]) => phrase);

  // Salutations
  const greetingWords = /^(salut|slt|coucou|cc|hey|hello|kikou|allo|allô|yo|bjr|bonsoir|bsr)/i;
  const greetings = [...new Set(
    yourTexts.filter(t => greetingWords.test(t.trim())).slice(0, 5)
  )];

  // Longueur moyenne
  const avgLen = yourTexts.length > 0
    ? Math.round(yourTexts.reduce((s, t) => s + t.length, 0) / yourTexts.length)
    : 50;

  return {
    realExamples: selectedPairs,
    commonEmojis: topEmojis,
    commonPhrases,
    avgMessageLength: avgLen,
    usesAbbreviations: detectAbbreviations(yourTexts),
    commonGreetings: greetings.length > 0 ? greetings : ["salut 💕", "coucou 🥰", "hey toi 😘"],
    commonSignoffs: [],
    totalMessagesAnalyzed: yourTexts.length,
    yourName,
  };
}

function selectDiverseExamples(
  pairs: { fanMessage: string; yourReply: string }[],
  count: number
): { fanMessage: string; yourReply: string }[] {
  if (pairs.length <= count) return pairs;

  // Catégories pour varier les exemples
  const short = pairs.filter(p => p.yourReply.length < 50);
  const medium = pairs.filter(p => p.yourReply.length >= 50 && p.yourReply.length < 120);
  const long = pairs.filter(p => p.yourReply.length >= 120);
  const withEmoji = pairs.filter(p => /\p{Emoji_Presentation}/u.test(p.yourReply));
  const questions = pairs.filter(p => p.fanMessage.includes("?"));

  const selected = new Set<{ fanMessage: string; yourReply: string }>();

  const pick = (arr: typeof pairs, n: number) => {
    const shuffled = arr.sort(() => Math.random() - 0.5);
    shuffled.slice(0, n).forEach(p => selected.add(p));
  };

  pick(short, Math.floor(count * 0.3));
  pick(medium, Math.floor(count * 0.3));
  pick(long, Math.floor(count * 0.15));
  pick(withEmoji, Math.floor(count * 0.15));
  pick(questions, Math.floor(count * 0.1));

  // Complète si besoin
  if (selected.size < count) pick(pairs, count - selected.size);

  return [...selected].slice(0, count);
}

export function buildStylePromptSection(profile: StyleProfile): string {
  const lines: string[] = [];

  lines.push(`=== TON STYLE RÉEL (exemples de tes vraies conversations) ===`);
  lines.push(`Tu as été analysée sur ${profile.totalMessagesAnalyzed} de tes vrais messages.`);
  lines.push(`Longueur moyenne de tes messages : ${profile.avgMessageLength} caractères.`);
  lines.push(``);

  if (profile.commonEmojis.length > 0) {
    lines.push(`Tes émojis préférés (utilise-les souvent) : ${profile.commonEmojis.join(" ")}`);
  }

  if (profile.usesAbbreviations) {
    lines.push(`Tu utilises des abréviations et du langage SMS (mdr, jsp, tfk, etc.)`);
  }

  if (profile.commonPhrases.length > 0) {
    lines.push(`Tes expressions récurrentes : ${profile.commonPhrases.slice(0, 8).join(" | ")}`);
  }

  lines.push(``);
  lines.push(`=== EXEMPLES RÉELS — imite EXACTEMENT ce style ===`);
  lines.push(`Voici des vraies conversations entre toi et tes fans. Reproduis ce ton à l'identique.`);
  lines.push(``);

  profile.realExamples.slice(0, 20).forEach((ex, i) => {
    lines.push(`Exemple ${i + 1}:`);
    lines.push(`Fan: "${ex.fanMessage}"`);
    lines.push(`Toi: "${ex.yourReply}"`);
    lines.push(``);
  });

  lines.push(`RÈGLE ABSOLUE : tes réponses doivent être INDISCERNABLES de ces exemples réels.`);

  return lines.join("\n");
}
