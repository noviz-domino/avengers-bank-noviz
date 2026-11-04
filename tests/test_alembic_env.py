from pathlib import Path

ROOT = Path(__file__).parent.parent


def test_env_imports_every_domain_model():
    # alembic check는 env.py가 import한 모델만 비교한다. 빠뜨리면 새 테이블이 조용히 무시된다.
    env = (ROOT / "alembic" / "env.py").read_text(encoding="utf-8")
    domains = ROOT / "src" / "avengers_bank" / "domains"
    missing = [
        p.parent.name
        for p in domains.glob("*/models.py")
        if f"avengers_bank.domains.{p.parent.name}.models" not in env
    ]
    assert not missing, f"alembic/env.py에 models import가 없는 도메인: {missing}"
