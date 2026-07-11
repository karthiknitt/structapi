import { defineAgent } from "eve";
import {
  CONTEXT_WINDOW_TOKENS,
  subagentModel,
} from "../../lib/openrouter.js";

export default defineAgent({
  model: subagentModel(),
  modelContextWindowTokens: CONTEXT_WINDOW_TOKENS,
  description:
    "RC slab design specialist per IS 456:2000 — one-way and two-way " +
    "(restrained Table 26 / simply-supported Annex D-2). Give it: panel " +
    "dimensions, edge continuity case, finishes + imposed loads, grades. " +
    "It returns thickness, bar callouts both directions (mid + edge strips), " +
    "shear and deflection checks, and corner torsion steel requirements.",
});
