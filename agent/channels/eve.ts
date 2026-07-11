import { eveChannel } from "eve/channels/eve";
import { none } from "eve/channels/auth";

// LOCAL-DEV-ONLY: `none()` disables channel auth entirely (steve pattern).
// Before deploying anywhere public, replace with real auth, e.g.:
//   auth: [localDev(), vercelOidc(), <your auth provider>]
export default eveChannel({
  auth: [none()],
});
