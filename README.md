# 렌주룰 오목 (사람 vs AI)

pygame으로 만든 15x15 렌주룰 오목입니다. 사람과 AI가 대결합니다.

## 규칙 (렌주룰)

- 흑이 먼저 두며, 첫 수는 천원(중앙)에 둡니다.
- 흑의 금수: **삼삼, 사사, 장목(6목 이상)** — 화면에 빨간 X로 표시됩니다.
- 흑은 정확히 5목일 때만 승리하며, 5목과 금수가 겹치면 5목이 우선합니다.
- 백은 5목 이상이면 승리하고 금수가 없습니다.

## 실행 방법

### 웹에서 바로 하기

**https://kyinkr.github.io/omok/** — 설치 없이 브라우저에서 실행됩니다.
(처음 로딩에 몇 초 걸리며, 웹 버전은 PC 버전보다 AI 계산이 느립니다.)

### 실행 파일 (Python 없이)

[Releases](../../releases) 페이지에서 `RenjuOmok.exe`를 내려받아 실행합니다.

### 소스로 실행

```bash
pip install -r requirements.txt
python main.py
```

Python 3.9 이상이 필요합니다.

## 조작

| 입력 | 동작 |
|---|---|
| 마우스 왼쪽 클릭 | 돌 두기 |
| `U` | 무르기 (내 수 + AI 수) |
| `N` | 수순 번호 표시 켜기/끄기 |
| `ESC` | 종료 |

오른쪽 패널에서 흑(선공)/백(후공) 선택과 AI 난이도(쉬움·보통·어려움)를 고를 수 있습니다.

## AI 난이도

| 난이도 | 생각 시간 | 특징 |
|---|---|---|
| 쉬움 | ~0.5초 | 2수 앞을 보고, 가끔 실수 |
| 보통 | ~1초 | 연속 4(VCF), 짧은 연속 위협(VCT 3수) 공격·방어 |
| 어려움 | ~4.5초 | 긴 연속 위협(VCT 8수) 공격, 위협 인식 탐색 |

## 파일 구성

| 파일 | 내용 |
|---|---|
| `main.py` | pygame 화면과 게임 진행 |
| `renju.py` | 렌주룰 판정 (금수, 승리) |
| `ai.py` | AI (VCF/VCT 탐색, 알파-베타 탐색) |
| `assets/` | 나눔고딕 폰트 (웹 버전 한글 표시용, [OFL](assets/OFL.txt)) |

## 배포

### 웹 (GitHub Pages)

`main` 브랜치에 push 하면 GitHub Actions가 [pygbag](https://github.com/pygame-web/pygbag)으로
웹(WebAssembly) 버전을 빌드해 GitHub Pages에 배포합니다.
처음 한 번은 저장소 **Settings → Pages → Source** 를 **GitHub Actions** 로 설정해야 합니다.

로컬에서 웹 버전 확인: `pip install pygbag` 후 `python -m pygbag .` → http://localhost:8000

### 실행 파일 (Windows)

`v`로 시작하는 태그를 올리면 GitHub Actions가 Windows 실행 파일을 빌드해 Releases에 올립니다.

```bash
git tag v1.0.0
git push origin v1.0.0
```
