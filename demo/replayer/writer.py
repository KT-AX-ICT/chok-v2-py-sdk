"""라이터 — 시프트한 줄을 `var/<모달리티>/<원본 파일명>` 에 append 한다 (계획 Phase 3).

이름도 내용도 바꾸지 않는다. 형식을 아는 코드는 콜렉터 하나이고, 여기는 받은 줄을 그대로 쓴다.

**이어 돌리기가 정상 경로다.** 시나리오를 바꿔 다시 실행하면 앞 실행 뒤에 이어 쌓인다. `--reset` 은
깨끗한 상태에서 다시 보기 위한 선택적 정리이지 재생의 전제가 아니다 (`ADR-004`).
"""

from __future__ import annotations

import shutil
from pathlib import Path
from types import TracebackType

# 콜렉터가 소유하는 모달리티 디렉터리 (`ADR-004`). `--reset` 이 지우는 것도 이 셋뿐이다.
MODALITIES = ("log", "metric", "trace")


def reset(source_root: Path) -> None:
    """`<source_root>/{log,metric,trace}` 를 비운다. 디렉터리 자체는 즉시 재생성해 남긴다.

    **`source_root` 자체를 `rmtree` 에 넘기지 않는다.** 이것이 방어의 전부다 — 경로가 어디로 잘못
    잡히든 날아가는 것은 그 밑의 이 세 폴더로 한정된다. `.replay/` 는 대상이 아니라 이력이 남는다.

    CWD 하위인지는 검사하지 않는다. 상대경로는 정의상 항상 CWD 하위라 오설정을 걸러내지 못하면서
    (`./var` 는 엉뚱한 CWD 에서도 통과한다) 절대경로 override 만 거부한다 (`ADR-004`).

    디렉터리를 지운 채로 두지 않는 이유 — SDK 의 `validate_source_layout()`(계획 06 §3)이 기동 시
    이 세 디렉터리의 존재를 확인한다. 지운 채로 두면, 리플레이어가 아직 데이터를 안 쓴 모달리티
    (trace 는 t0+126초까지 지연)만큼 그 사이에 rca-collect 가 기동 실패한다. `--reset` 을 먼저
    실행하고 나서 rca-collect 를 띄우는 순서에서도 즉시 안전하도록, 내용만 비우고 빈 디렉터리는
    바로 되돌려준다.
    """
    for name in MODALITIES:
        d = source_root / name
        if d.is_dir():
            shutil.rmtree(d)
        d.mkdir(parents=True, exist_ok=True)


class Writer:
    """모달리티별 출력 파일을 열어두고 줄을 흘려보낸다.

    파일 핸들을 재생 내내 붙들고 있는다 — 줄마다 여닫으면 100만 번 열게 된다. 27개라 문제없다.
    """

    def __init__(self, source_root: Path) -> None:
        self._root = source_root
        self._files: dict[tuple[str, str], object] = {}

    def path_for(self, modality: str, filename: str) -> Path:
        if modality not in MODALITIES:
            raise ValueError(f"알 수 없는 모달리티: {modality!r}")
        return self._root / modality / filename

    def open(self, modality: str, filename: str, header: str | None = None):
        """출력 파일을 연다. `header` 가 있고 **파일이 없거나 0바이트일 때만** 헤더를 쓴다.

        이미 내용이 있는 파일에 헤더를 또 쓰면 파일 중간에 헤더가 데이터 행인 척 끼어들고,
        tail 하는 쪽이 `timestamp` 를 시각으로 파싱하려다 실패한다. 3종 시나리오는 CSV 파일명도
        헤더도 같아서 시나리오를 바꿔 이어 돌리면 바로 걸린다.
        """
        key = (modality, filename)
        if key in self._files:
            return self._files[key]

        path = self.path_for(modality, filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        fresh = not path.exists() or path.stat().st_size == 0

        # 리더와 같은 조건으로 연다 — `newline=""` 로 개행 변환을 끄고 `surrogateescape` 로
        # 비 UTF-8 바이트를 되돌려, 받은 줄이 원본과 바이트 동일하게 나간다.
        # `buffering=1` (줄 단위) — 버퍼에 쌓아두면 tailer 가 실시간으로 못 본다.
        f = open(path, "a", encoding="utf-8", errors="surrogateescape", newline="", buffering=1)
        self._files[key] = f
        if header is not None and fresh:
            f.write(header)
        return f

    def write(self, modality: str, filename: str, line: str) -> None:
        self._files[(modality, filename)].write(line)

    def close(self) -> None:
        for f in self._files.values():
            f.close()
        self._files.clear()

    def __enter__(self) -> Writer:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()
