import { defineSandbox } from "eve/sandbox";
import { docker } from "eve/sandbox/docker";

// Same hardened image as the root agent: numpy/matplotlib baked in,
// deny-all egress. The iscodes library is seeded via sandbox/workspace/
// (populated by scripts/sync-workspace.mjs — run it after editing python/).
export default defineSandbox({
  backend: docker({
    image: "structagent-sandbox:latest",
    pullPolicy: "if-not-present",
    networkPolicy: "deny-all",
  }),
});
