from __future__ import annotations

import logging
import os
import sys

from configs import settings

logger = logging.getLogger("ai-platform.startup")


def validate_environment() -> list[str]:
    """Check that the runtime environment is sane.

    Returns a list of warning messages (empty = all good).
    """
    warnings: list[str] = []

    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
        if not os.environ.get(key):
            provider = key.replace("_API_KEY", "").lower()
            if getattr(settings, f"enable_{provider}", False):
                warnings.append(
                    f"{key} is not set — {provider} provider will not work"
                )

    return warnings


def print_startup_banner() -> None:
    """Print a diagnostic banner on startup."""
    banner = f"""
{'=' * 54}
  {settings.app_name} v0.1.0
  Log level : {settings.log_level}
  JSON logs : {settings.log_json}
  Debug     : {settings.debug}
{'=' * 54}
"""
    print(banner, file=sys.stderr)


def log_provider_status() -> None:
    """Log which providers are enabled and configured."""
    logger.info("Provider status:")
    for provider, enabled in settings.providers_enabled.items():
        has_key = settings.provider_keys_present.get(provider, False)
        status = "enabled" if enabled else "disabled"
        key_status = "key present" if has_key else "no key configured"
        logger.info("  %-10s  %s  (%s)", provider, status, key_status)


def run_startup_checks() -> None:
    """Run all startup diagnostics."""
    print_startup_banner()

    warnings = validate_environment()
    for w in warnings:
        logger.warning("env: %s", w)

    log_provider_status()

    if warnings:
        logger.info("Startup complete with %d warning(s)", len(warnings))
    else:
        logger.info("Startup complete — all checks passed")
