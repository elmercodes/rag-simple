import { apiBaseUrl } from "@/lib/config";

const sampleResponses = [
  "Let me break that down into a few clear steps so you can move fast.",
  "Here's a concise summary along with a suggested next action.",
  "I can help draft a plan and outline the risks before you build.",
  "Great question. The short answer is yes, and here's why it matters."
];

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function pickSeededResponse(prompt: string) {
  const seed = prompt.split("").reduce((acc, char) => acc + char.charCodeAt(0), 0);
  return sampleResponses[seed % sampleResponses.length];
}

export async function* mockStreamAssistantReply(
  prompt: string,
  useDocs: boolean,
  model: string
) {
  // TODO: Replace with real streaming API call using apiBaseUrl.
  void apiBaseUrl;
  void model;
  const intro = pickSeededResponse(prompt);
  const modeHint = useDocs
    ? "I'll lean on the documents you've shared."
    : "I'll answer generally without pulling from your docs.";
  const body =
    `\n\n${modeHint}\n\n` +
    "- Clarify intent\n" +
    "- Draft a minimal response\n" +
    "- Validate assumptions\n" +
    "- Iterate with feedback";
  const full = `${intro}${body}`;

  const chunks = full.match(/.{1,14}/g) ?? [full];
  for (const chunk of chunks) {
    await sleep(45);
    yield chunk;
  }
}
