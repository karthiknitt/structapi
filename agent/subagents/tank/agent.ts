import { defineAgent } from "eve";
import {
  CONTEXT_WINDOW_TOKENS,
  subagentModel,
} from "../../lib/openrouter.js";

export default defineAgent({
  model: subagentModel(),
  modelContextWindowTokens: CONTEXT_WINDOW_TOKENS,
  description:
    "Water tank design specialist per IS 3370 Parts 1-4 (2021): ground-" +
    "supported circular and rectangular RC tanks. Give it: capacity or " +
    "dimensions, water depth, wall base condition (hinged/fixed), grades " +
    "(min M30). It returns wall forces (hoop tension / moments from IS " +
    "3370-4 coefficients), wall thickness and reinforcement governed by the " +
    "0.1/0.2 mm crack-width limits, and clause-referenced checks.",
});
