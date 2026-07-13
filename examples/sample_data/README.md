# sample_data

SN 데이터 발췌 (git 커밋 대상 아님 — `scripts/generate_sample_data.py` 로 로컬 생성).

권장 구성:
```
sample_data/
├── cpu/          # Perf_CPU_Contention 발췌
├── kill_media/   # Svc_Kill_Media 발췌
└── code_media/   # Code_Stop_MediaService 발췌
```
각 폴더에 log/metric/trace 최소 샘플을 둔다.
