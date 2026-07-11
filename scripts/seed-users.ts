// Seed test users for local testing (email+password, no verification).
// Requires the Postgres container up and auth tables migrated:
//   pnpm db:up && pnpm auth:migrate && pnpm seed:users
// Node 24 runs this TypeScript file directly (type stripping).
import { auth } from "../lib/auth.ts";

const USERS = [
  { name: "Umashankar", email: "umashankar@simplicontract.com", password: "StructAgent@2026" },
  { name: "Test Engineer", email: "engineer@structagent.test", password: "Engineer@123" },
  { name: "Test Viewer", email: "viewer@structagent.test", password: "Viewer@123" },
];

for (const user of USERS) {
  try {
    await auth.api.signUpEmail({ body: user });
    console.log(`created: ${user.email}  (password: ${user.password})`);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    if (/exist/i.test(msg)) {
      console.log(`exists:  ${user.email}`);
    } else {
      console.error(`FAILED:  ${user.email} — ${msg}`);
      process.exitCode = 1;
    }
  }
}
process.exit();
