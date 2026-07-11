import { betterAuth } from "better-auth";
import { Pool } from "pg";

// BetterAuth server instance. Uses the SAME Postgres container as the eve
// workflow world (docker-compose service `postgres`, host port 5544); auth
// tables (user/session/account/verification) live alongside the workflow
// schema. Run `pnpm auth:migrate` once after `pnpm db:up` to create them.
export const auth = betterAuth({
  database: new Pool({
    connectionString:
      process.env.AUTH_DATABASE_URL ??
      process.env.WORKFLOW_POSTGRES_URL ??
      "postgres://world:world@localhost:5544/world",
  }),
  baseURL: process.env.BETTER_AUTH_URL ?? "http://localhost:3001",
  secret: process.env.BETTER_AUTH_SECRET,
  socialProviders: {
    google: {
      clientId: process.env.GOOGLE_CLIENT_ID ?? "",
      clientSecret: process.env.GOOGLE_CLIENT_SECRET ?? "",
    },
  },
});

export type Session = typeof auth.$Infer.Session;
