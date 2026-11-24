"""Local vault key, generated once outside the tracked repository contents."""
from functools import lru_cache
import json
import os
from pathlib import Path
import tempfile

from ..config import INSTANCE_DIR
from . import aes_gcm


@lru_cache(maxsize=1)
def key():
    path = Path(INSTANCE_DIR) / "workbench_vault.key"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        # Publish a fully written key atomically; a concurrent worker keeps the
        # winner's key rather than overwriting it or reading a partially written file.
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix="vault-", delete=False) as f:
            temp = Path(f.name)
            f.write(os.urandom(32))
            f.flush()
            os.fsync(f.fileno())
        try:
            try:
                os.link(temp, path)
            except FileExistsError:
                pass
        finally:
            temp.unlink(missing_ok=True)
    value = path.read_bytes()
    if len(value) != 32:
        raise ValueError("本地数据密钥损坏，请恢复 instance/workbench_vault.key，不能重新生成替代密钥")
    return value


def encrypt(value):
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return aes_gcm.encrypt(key(), raw), len(raw)


def decrypt(token):
    return json.loads(aes_gcm.decrypt(key(), token).decode("utf-8"))
