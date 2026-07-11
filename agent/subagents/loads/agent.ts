import { defineAgent } from "eve";
import {
  CONTEXT_WINDOW_TOKENS,
  subagentModel,
} from "../../lib/openrouter";

export default defineAgent({
  model: subagentModel(),
  modelContextWindowTokens: CONTEXT_WINDOW_TOKENS,
  description:
    "Load computation specialist per IS 875 Parts 1-3 and IS 1893:2016. " +
    "Give it: building geometry (storeys, heights, plan dims), occupancy, " +
    "location/city (or basic wind speed + seismic zone), terrain category, " +
    "soil type, and frame type. It returns dead/imposed loads, wind design " +
    "pressures (IS 875-3:2015), equivalent-static seismic base shear with " +
    "storey distribution (IS 1893:2016), and all IS 456 Table 18 load " +
    "combinations ranked by severity.",
});
