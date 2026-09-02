import { defineInstrumentation } from "eve/instrumentation";
import { registerOTel } from "@vercel/otel";

// Ships spans to Langfuse over its OTLP endpoint. Set LANGFUSE_PUBLIC_KEY /
// LANGFUSE_SECRET_KEY (and LANGFUSE_BASE_URL for self-hosted or a non-EU
// region) in the environment. With neither key set, this still registers
// local Vercel Workflow run tags and OTel spans against the loopback OTLP
// default (http://localhost:4318) — i.e. it's a no-op export, not a crash.
export default defineInstrumentation({
  setup: ({ agentName }) => {
    const publicKey = process.env.LANGFUSE_PUBLIC_KEY;
    const secretKey = process.env.LANGFUSE_SECRET_KEY;
    const baseUrl = process.env.LANGFUSE_BASE_URL ?? "https://cloud.langfuse.com";

    if (publicKey && secretKey) {
      process.env.OTEL_EXPORTER_OTLP_ENDPOINT = `${baseUrl}/api/public/otel`;
      process.env.OTEL_EXPORTER_OTLP_HEADERS =
        `Authorization=Basic ${Buffer.from(`${publicKey}:${secretKey}`).toString("base64")},` +
        "x-langfuse-ingestion-version=4";
    }

    return registerOTel({
      serviceName: agentName,
      traceExporter: "auto",
    });
  },
});
