"""SDK 설정. 환경변수(prefix RCA_) 또는 .env 에서 로드한다."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RCA_", env_file=".env", extra="ignore")

    # 전송 대상
    collect_endpoint: str = "http://localhost:8000/v1/ingest"

    # 관측 루프
    loop_interval_sec: int = 30

    # 버퍼 / 스냅샷 윈도  (docs/decisions/ADR-001 참조)
    buffer_window_sec: int = 210        # 3분 30초 롤링 윈도
    post_trigger_wait_sec: int = 180    # 트리거 후 3분 post 수집

    # 원천 로그 경로 - tail이 추적하는 데이터 경로
    source_root: str = "./var"

    # 원본 데이터셋 경로 - 리플레이어가 source_root로 전달할 데이터셋 경로
    dataset_root: str = "./datasets/sn"

    # 기대 서비스 로스터 (canonical, 계획 03 §3) — missing 판정의 관측 밖 기준
    expected_services: list[str] = [
        "media", "nginx", "user", "text", "uniqueid", "urlshorten",
        "usermention", "usertimeline", "hometimeline", "poststorage",
        "composepost", "socialgraph",
    ]


def load_settings() -> Settings:
    """설정 로드 진입점 (테스트에서 override 하기 쉽게 함수로 감쌈)."""
    return Settings()
