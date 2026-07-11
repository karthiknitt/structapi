import { defineAgent } from "eve";
import {
  CONTEXT_WINDOW_TOKENS,
  subagentModel,
} from "../../lib/openrouter.js";

export default defineAgent({
  model: subagentModel(),
  modelContextWindowTokens: CONTEXT_WINDOW_TOKENS,
  description:
    "Concrete mix design specialist per IS 10262:2019. Give it: grade, " +
    "exposure class, max aggregate size, target slump, fine-aggregate zone, " +
    "admixture intent, and specific gravities if known. It returns the full " +
    "first-trial mix: target strength, governing w/c (strength vs " +
    "durability), water/cement/aggregate quantities per m3, mix ratio, " +
    "and trial-mix guidance, with IS 456 Table 5 durability checks.",
});
