# CRIA 서랍 열기 공개 데모

CRIA 149번의 녹화 영상과 힘·토크 기록을 재생하는 정적 웹 데모다.
`index.html`은 저장된 경보와 현장 확인 항목을, `live.html`은 재생 시점까지 받은 기록으로 새로 계산한 Random Forest 점수를 보여준다.

## 로컬 실행

이 폴더에서 `python -m http.server 8000`을 실행하고 `http://localhost:8000/`을 연다.
실제 센서 연결은 기기의 출력 방식에 맞춘 후속 작업이다.

## 원본과 출처

- [프로젝트 코드·실습 노트북·모델 비교](https://github.com/lifeschedule-dotcom/cria-drawer-anomaly-detection/tree/main)
- [CRIA 원본](https://huggingface.co/datasets/Joringell/CRIA), CC BY 4.0. 제작자와 가공 내용은 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)에 정리했다.
- [SafetyDesigner 위험성평가 공개 가이드](https://doc.safetics.io/docs/ra-est-eval/)

이 `gh-pages` 브랜치의 루트가 GitHub Pages 공개 원본이다.
