GENERIC_ACK_PREFIXES: tuple[str, ...] = (
    "已记录",
    "已经记录",
    "记录了",
    "收到",
    "好的",
    "明白",
)


def is_generic_ack(text: str) -> bool:
    compact = text.strip()
    return any(compact.startswith(prefix) for prefix in GENERIC_ACK_PREFIXES)
