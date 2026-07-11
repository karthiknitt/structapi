import type { NextConfig } from "next";
import { withEve } from "eve/next";

// Keep the Next.js app isolated from the agent's own tsconfig.json (used by
// `tsc` / `eve build`) so neither build interferes with the other.
const nextConfig: NextConfig = {
  typescript: {
    tsconfigPath: "tsconfig.next.json",
  },
};

// withEve mounts /eve/v1/* routes on this Next app's origin, proxying to a
// locally-started `eve dev` server (or the deployed eve service in
// production).
export default withEve(nextConfig);
