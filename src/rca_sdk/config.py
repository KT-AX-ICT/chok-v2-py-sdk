"""SDK 설정. 환경변수(prefix RCA_) 또는 .env 에서 로드한다."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RCA_", env_file=".env", extra="ignore")

    # 전송 대상
    collect_endpoint: str = "http://localhost:8000/ingest"

    # 관측 루프
    loop_interval_sec: int = 30

    # 버퍼 / 스냅샷 윈도  (docs/decisions/ADR-001 참조)
    #
    # 보존은 pre 윈도(PRE_SEC=180)와 **다른 값**이다. "window" 라는 이름이 스냅샷 창과 같아야
    # 하는 것처럼 읽혀 한때 180 으로 되돌려진 적이 있어 retention 으로 개명했다.
    # 210 = PRE_SEC(180) + 루프 주기(30). 유도는 계획 04 §1.
    buffer_retention_sec: int = 210     # 버퍼가 레코드를 들고 있는 기간
    post_trigger_wait_sec: int = 180    # 트리거 후 3분 post 수집

    # 원천 로그 경로 - tail이 추적하는 데이터 경로
    source_root: str = "./var"

    # 원본 데이터셋 경로 - 리플레이어가 source_root로 전달할 데이터셋 경로
    dataset_root: str = "./datasets/sn"

    # detector 조건 (ADR-006 §미결 "실 임계값 도출" 의 확정치, 계획 05 R2)
    #
    # 임계는 코드에 박지 않고 여기서만 주입한다(계약 §0-5). detector_type -> condition.
    # 값 근거는 ADR-006 — 실데이터 분포로 도출했고, 배선만 러너 단계로 미뤄져 있었다.
    trigger_conditions: dict[str, dict[str, float | int | str]] = {
        # host CPU plateau. bar 초과 샘플이 창 안에 min_over 개 이상.
        # baseline 최장 런 3 vs 주입 23 이라 5 는 양쪽에 여유가 있다.
        "cpu_spike": {"bar": 50, "min_over": 5, "window_sec": 210},
        # 부팅 마커 2회 = kill 후 재시작. 정상 부팅은 1회.
        "restart_marker": {"threshold": 2, "baseline": 1.0, "window_sec": 210},
        # 500 span — baseline 0, Code_Stop 70~98건.
        "trace_5xx": {"baseline": 0, "floor": 3},
        # connection_error — baseline 0, 결함 시 ~11/분(≈5.5/30초).
        "nginx_error": {"baseline": 0, "floor": 3},
        # perf log 는 duplicate-key artifact 라 무신호. baseline 아티팩트율(~5/30초) 위로
        # 두어 거의 침묵시킨다 — 발화하면 그게 오탐 신호다.
        "error_rate": {"baseline": 5, "ratio": 1.5, "floor": 8},
        # OUT p50 11.6ms -> IN 21.3ms. 전체 창 희석 주의.
        "latency_spike": {"baseline": 11.6, "ratio": 1.8, "floor": 20},
    }

    # 기대 서비스 로스터 (canonical, 계획 03 §3) — missing 판정의 관측 밖 기준
    expected_services: list[str] = [
        "media", "nginx", "user", "text", "uniqueid", "urlshorten",
        "usermention", "usertimeline", "hometimeline", "poststorage",
        "composepost", "socialgraph",
    ]

    # 로그 truncate — 번들 용량 상한 보장 (2026-07-23 설계, service+level 축).
    #
    # 대상: level=="info" AND event_type=="normal_log" AND service 가 이번 세션 trigger 근거에
    # 없는 레코드만. error/warn·service_start/connection_error·trigger 귀속 서비스는 절대 안 자름.
    # cap 초과 시 균등 간격(stride) 샘플링 — head-N 이 아니라 창 전체 모양을 유지한다.
    #
    # backstop_cap 은 exempt 레코드를 포함한 서비스별 최후 상한 — 정상 동작에서는 절대 안 걸리고,
    # trigger 귀속 서비스 자체가 폭주하는 미지의 사태에 대한 번들 크기 상한 보장용이다.
    log_truncation_enabled: bool = True
    log_truncation_cap: int = 5000
    log_truncation_backstop_cap: int = 50000


def load_settings() -> Settings:
    """설정 로드 진입점 (테스트에서 override 하기 쉽게 함수로 감쌈)."""
    return Settings()
