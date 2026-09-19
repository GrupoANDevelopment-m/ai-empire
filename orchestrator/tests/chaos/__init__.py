"""
Chaos tests — actually start/stop/kill services.

These are DANGEROUS. They require:
  - EMPIRE_CHAOS_TESTS=1 environment variable
  - docker compose available
  - careful cleanup

Only run in dedicated test environments, never in shared ones.
"""
