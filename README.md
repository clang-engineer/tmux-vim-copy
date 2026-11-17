# tmux-vim-copy

별도 뷰어 없이 **실제 tmux Copy Mode 화면**에 Vim 스타일 선택과 텍스트 객체를 더하는 독립 플러그인입니다. tmux 버퍼와 기존 Copy Mode 이동·검색을 그대로 사용하며, Python 3 표준 라이브러리만 필요합니다.

대상 환경은 Python 3.9+, tmux 3.7+입니다. Copy Mode 스냅샷과 줄바꿈 정보를 보존하는 `capture-pane -M` / `-F` 기능이 필요하며 설치 시 기능 지원 여부를 확인합니다. 기본 셸 진입점은 macOS 기본 Bash 3.2와 호환되도록 작성했습니다.

## 설치

### TPM

플러그인 선언을 TPM 실행 줄 앞에 추가한 뒤 `prefix + I`로 설치합니다.

```tmux
set -g @plugin 'clang-engineer/tmux-vim-copy'
```

tmux-open을 함께 쓰면 tmux-open 뒤에 선언합니다. 설치 시 `mode-keys`를
`vi`로 설정하고 필요한 키만 덮어쓰며, 기존 키 테이블 전체를 초기화하지 않습니다.

### 수동 설치·로컬 개발

```sh
git clone https://github.com/clang-engineer/tmux-vim-copy ~/.tmux/plugins/tmux-vim-copy
```

`~/.tmux.conf`에 다음을 추가하고 리로드합니다.

```tmux
run-shell '~/.tmux/plugins/tmux-vim-copy/vim-copy.tmux'
```

실행 중인 tmux 세션에서는 체크아웃의 진입점을 직접 실행할 수도 있습니다.

```sh
bash /absolute/path/to/tmux-vim-copy/vim-copy.tmux
```

## 키

기본 tmux prefix + `[`로 Copy Mode에 들어갑니다.

| 키 | 동작 |
| --- | --- |
| `v` / `V` / `Ctrl-v` | 문자 / 줄 / 사각형 선택 |
| `y` | 선택 영역 복사; 선택이 없으면 `yy`로 현재 줄 복사 |
| `O` | 선택의 양 끝점 교환 |
| `iw` / `aw`, `iW` / `aW` | 단어 / 공백 기준 WORD의 안쪽·바깥쪽 선택 |
| `ip` / `ap` | 문단 안쪽·바깥쪽 선택 |
| `i"`, `i'`, `` i` `` 및 대응하는 `a` 조합 | 따옴표 안쪽·바깥쪽 선택; 이스케이프 처리 |
| `i(`, `i{`, `i[`, `i<` 및 대응하는 `a` 조합 | 여러 줄에 걸친 중첩 괄호 안쪽·바깥쪽 선택 |
| `ib` / `ab`, `iB` / `aB` | 각각 `()`와 `{}`의 별칭 |
| `i)`, `i}`, `i]`, `i>` 및 대응하는 `a` 조합 | 닫는 괄호 키도 같은 객체 선택 |
| `gg` / `ge` / `gE` | 버퍼 처음 / 이전 단어 끝 / 이전 WORD 끝 |
| `zt` / `zz` / `zb` | 커서 줄을 화면 위 / 가운데 / 아래로 이동 |

`i`/`a`/`g`/`z` 및 선택 없는 첫 `y` 뒤의 대기 상태에서는 `Escape`, `Ctrl-c`, `q` 또는 지원하지 않는 키로 취소할 수 있습니다. 이때 Copy Mode를 나가지 않습니다. 비어 있거나 짝이 맞지 않는 객체는 커서와 기존 선택을 바꾸지 않고 메시지를 표시합니다.

기존 tmux 단어 이동, 검색, 숫자 반복은 그대로입니다. 예를 들어 `3w`는 tmux 기본 동작입니다. 새 Python 동작의 숫자 접두사(`3iw` 등)는 지원하지 않습니다.

`g`와 `z`는 두 번째 키를 기다리는 접두사가 됩니다. 기본 tmux의 단일 `g` 동작은 `gg`, 단일 `z` 동작은 `zz`로 사용합니다. 문자·줄·블록 모드에서 같은 선택 키를 다시 누르면 선택을 해제하고 Copy Mode는 유지합니다.

## 옵션

설치/재로드 전에 설정합니다.

```tmux
set -g @vim-copy-yank-exit 'on'
set -g @vim-copy-swap-key 'O'
set -g @vim-copy-python 'python3'
```

- `@vim-copy-yank-exit`: 기본 `on`은 복사 후 Copy Mode를 종료합니다. `off`는 복사 후 선택과 Copy Mode를 유지합니다.
- `@vim-copy-swap-key`: 끝점 교환 키, 기본 `O`입니다. 다른 키로 바꾸면 해당 키의 기존 바인딩을 덮어쓸 수 있습니다.
- `@vim-copy-python`: Python 실행 파일 이름 또는 절대 경로입니다. 인수는 넣지 않습니다. 설치 시 환경 변수 `TMUX_VIM_COPY_PYTHON`이 이 옵션보다 우선하며, 둘 다 없으면 `python3`를 사용합니다.

```sh
TMUX_VIM_COPY_PYTHON=/absolute/path/to/python3 bash /absolute/path/to/tmux-vim-copy/vim-copy.tmux
```

기본 교환 키는 대문자 `O`이므로 tmux-open의 `o`, `Ctrl-o`, `S`를 차지하지 않습니다. 기존 Copy Mode UI와 tmux-open은 계속 사용하며 별도 뷰어를 띄우지 않습니다.

## 한계와 안전

- 텍스트 객체는 tmux가 보유한 텍스트를 기준으로 찾습니다. 프로그래밍 언어의 주석·문자열·문법을 해석하는 파서가 아닙니다. 복잡한 코드에서는 기대와 다른 괄호/따옴표 쌍이 선택될 수 있습니다.
- 따옴표 객체는 논리적인 한 줄 안에서 찾습니다. 괄호 객체는 중첩과 여러 줄을 처리하며, 터미널 폭 때문에 접힌 줄은 논리적인 원문으로 합칩니다. 단어는 Unicode 문자·숫자·밑줄·결합 부호와 문장부호를 구분하고, WORD는 공백으로 구분합니다. Vim의 `iskeyword` 설정을 가져오지는 않습니다.
- CJK 전각 문자와 결합 부호의 셀 좌표를 처리합니다. ZWJ·variation selector·피부색 modifier·국기 조합 같은 복합 emoji가 있는 줄의 helper 기반 선택은 명시적으로 거부하고 기존 선택을 유지합니다. 해당 줄에서는 tmux의 기본 이동·선택을 사용하세요.
- `ip`는 빈 줄 경계를 제외한 문단을 줄 단위로 선택하고, `ap`는 뒤쪽 빈 줄(없으면 앞쪽 빈 줄)을 포함합니다. 빈 안쪽 객체나 짝이 없는 괄호는 잘못된 영역을 선택하지 않습니다.
- 설치된 코드와 Python 실행 파일은 신뢰할 수 있는 것만 사용하세요. 이 플러그인은 선택한 텍스트를 셸 명령에 보간하거나 실행하지 않습니다. tmux-open 등 다른 플러그인의 실행 동작은 그 플러그인의 정책을 따릅니다.
- 복사는 tmux 버퍼를 사용합니다. 시스템 클립보드 연동은 기존 tmux 환경 설정에 따릅니다.

## 개발 및 참고

```sh
make test
make lint
```

`make test`는 표준 라이브러리 `unittest`를 실행합니다. `make lint`는 외부 도구 없이 Python 구문을 컴파일하며 바이트코드 파일을 만들지 않습니다.

현재 로컬 검증 환경은 macOS, tmux 3.7c, Python 3.15입니다. 순수 텍스트 객체 테스트와 격리 소켓의 실제 tmux 클라이언트 테스트를 실행합니다. Linux와 macOS CI 설정도 포함하지만 CI 실행 결과를 로컬 검증으로 대신 주장하지 않습니다.

동작과 시각적 선택 상태에 관한 참고: [pwnalone/tmux-vi-copy-mode](https://github.com/pwnalone/tmux-vi-copy-mode), [shitcoding/tmux_yankee](https://github.com/shitcoding/tmux_yankee) (각 MIT). 이 프로젝트는 해당 프로젝트의 포크가 아니며 코드를 복사하지 않은 독립 구현입니다.

MIT 라이선스. Copyright (c) 2026 clang-engineer.
