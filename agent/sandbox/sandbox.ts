import { defineSandbox } from "eve/sandbox";
import { docker } from "eve/sandbox/docker";

// Docker sandbox backend (steve pattern). NOTE: requires Docker Desktop and
// the locally built image: `docker build -t structagent-sandbox:latest sandbox-image/`
// networkPolicy is set at the factory level (eve 0.15.0 quirk): deny-all
// egress means model-generated code can never phone home — all Python deps
// are baked into the image.
export default defineSandbox({
  backend: docker({
    image: "structagent-sandbox:latest",
    pullPolicy: "if-not-present",
    networkPolicy: "deny-all",
  }),
});
