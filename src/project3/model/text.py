"""Xử lý văn bản log dùng chung cho mô hình, baseline và LLM."""


def mask_text(text: str, key: str) -> str:
    """Che bằng chứng: xoá mọi dòng chứa dòng bằng chứng của quy tắc (key), giữ nguyên phần còn lại."""
    return "\n".join(l for l in text.splitlines() if key not in l) if key else text


def clip_chunk(text: str, n: int = 1100) -> str:
    """Giữ dòng đầu (ranh giới goal/task) + phần cuối đoạn; đủ dư cho 256 token."""
    first, _, rest = text.partition("\n")
    return first[:200] + ("\n" + rest[-n:] if rest else "")


def ci_context(workflow: str, job: str, step: str) -> str:
    """Ngữ cảnh CI của run, mã hoá cùng encoder với log."""
    return f"workflow: {workflow} | job: {job} | step: {step}"
