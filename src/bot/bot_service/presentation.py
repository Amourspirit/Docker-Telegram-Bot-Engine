from __future__ import annotations


def build_help_text(
    action_names: list[str],
    action_handler_counts: dict[str, int],
    action_aliases: dict[str, tuple[str, ...]] | None = None,
) -> str:
    lines = ["🤖 Available Commands"]
    action_aliases = action_aliases or {}
    for action_name in sorted(action_names):
        handler_count = action_handler_counts.get(action_name, 0)
        aliases = action_aliases.get(action_name, ())
        alias_suffix = ""
        if aliases:
            alias_suffix = " (aliases: " + ", ".join(f"/{alias_name}" for alias_name in aliases) + ")"
        lines.append(f"/{action_name} - {handler_count} handler(s){alias_suffix}")

    lines.append("/reload_actions - Reload host action config")
    lines.append("/action_info <action> - Show policy and handler stages")
    return "\n".join(lines)


def build_action_info_text(action_name: str, details: dict[str, object]) -> str:
    policy = details["policy"]
    stages = details["stages"]
    aliases = details.get("aliases", [])

    lines = [f"Action: /{action_name}"]
    if aliases:
        lines.append("Aliases: " + ", ".join(f"/{alias_name}" for alias_name in aliases))
    lines.append(f"stop_on_failure: {policy['stop_on_failure']}")
    lines.append(f"default_timeout_seconds: {policy['default_timeout_seconds']}")
    lines.append("Stages:")

    for idx, stage in enumerate(stages):
        if not stage:
            lines.append(f"  stage {idx}: (no handlers)")
            continue

        lines.append(f"  stage {idx}:")
        for handler in stage:
            lines.append(
                "    - "
                f"{handler['handler_id']} "
                f"(stop_on_failure={handler['stop_on_failure']}, "
                f"timeout_seconds={handler['timeout_seconds']})"
            )

    return "\n".join(lines)