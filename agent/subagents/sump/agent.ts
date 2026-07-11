import { defineAgent } from "eve";
import {
  CONTEXT_WINDOW_TOKENS,
  subagentModel,
} from "../../lib/openrouter";

export default defineAgent({
  model: subagentModel(),
  modelContextWindowTokens: CONTEXT_WINDOW_TOKENS,
  description:
    "Underground sump/tank design specialist per IS 3370 (2021) with earth " +
    "pressure and groundwater. Give it: internal dims, depth below ground, " +
    "soil properties (gamma, phi, surcharge), water table depth, grades. It " +
    "handles both governing cases (full/no-backfill and empty/backfilled), " +
    "the uplift-flotation check (FOS >= 1.2), and crack-width-governed wall/" +
    "base design with clause-referenced checks.",
});
