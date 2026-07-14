from __future__ import annotations


def build_help_text(action_names: list[str], action_handler_counts: dict[str, int]) -> str:
    lines = ["🤖 **Available Commands**"]
    for action_name in sorted(action_names):
        handler_count = action_handler_counts.get(action_name, 0)
        lines.append(f"/{action_name} - {handler_count} handler(s)")

    lines.append("/reload_actions - Reload host action config")
    lines.append("/action_info <action> - Show policy and handler stages")
    return "\n".join(lines)


def build_action_info_text(action_name: str, details: dict[str, object]) -> str:
    policy = details["policy"]
    stages = details["stages"]

    lines = [f"Action: /{action_name}"]
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