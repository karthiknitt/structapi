"""structapi — deterministic REST facade over the iscodes IS-code engine.

v1 contract: docs/PLANFORGE-INTEGRATION.md. No engineering logic lives here;
every route validates input, calls iscodes, and wraps the frozen envelope.
"""

API_VERSION = "1"
