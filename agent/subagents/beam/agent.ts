import { defineAgent } from "eve";
import {
  CONTEXT_WINDOW_TOKENS,
  subagentModel,
} from "../../lib/openrouter";

export default defineAgent({
  model: subagentModel(),
  modelContextWindowTokens: CONTEXT_WINDOW_TOKENS,
  description:
    "RC beam design specialist per IS 456:2000 (Limit State Method). " +
    "Give it: span, support condition (simply supported / cantilever / fixed / " +
    "continuous), characteristic dead + imposed loads (kN/m and point loads), " +
    "concrete grade, steel grade, exposure, and whether seismic detailing " +
    "(IS 13920) applies. It returns flexure + shear + deflection design with " +
    "bar callouts, all clause-referenced checks, and SFD/BMD PNG plots " +
    "(BMD on tension side per Indian convention).",
});
