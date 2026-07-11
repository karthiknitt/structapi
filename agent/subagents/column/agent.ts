import { defineAgent } from "eve";
import {
  CONTEXT_WINDOW_TOKENS,
  subagentModel,
} from "../../lib/openrouter";

export default defineAgent({
  model: subagentModel(),
  modelContextWindowTokens: CONTEXT_WINDOW_TOKENS,
  description:
    "RC column design specialist per IS 456:2000 cl 25/39 (LSM) with IS " +
    "13920:2016 ductile detailing. Give it: factored axial load Pu, moments " +
    "Mux/Muy, unsupported/effective lengths, trial section and grades, and " +
    "whether seismic. It returns short/slender classification, biaxial P-M " +
    "interaction verification (cl 39.6), tie/confinement detailing, and a " +
    "P-M interaction diagram PNG with the design point marked.",
});
