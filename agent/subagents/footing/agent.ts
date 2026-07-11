import { defineAgent } from "eve";
import {
  CONTEXT_WINDOW_TOKENS,
  subagentModel,
} from "../../lib/openrouter.js";

export default defineAgent({
  model: subagentModel(),
  modelContextWindowTokens: CONTEXT_WINDOW_TOKENS,
  description:
    "Foundation design specialist: isolated footings (axial + moment) and " +
    "two-column combined footings per IS 456:2000 cl 34/31.6, with bearing " +
    "capacity per IS 6403 when soil parameters are given. Give it: column " +
    "loads (service), column sizes, SBC (or c-phi soil data), concrete/steel " +
    "grades. It returns plan dims, depth, reinforcement both ways, punching/" +
    "one-way shear checks, pressure diagrams, and for combined footings the " +
    "longitudinal SFD/BMD PNGs.",
});
