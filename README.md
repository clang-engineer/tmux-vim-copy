# tmux-vim-copy

An independent plugin that adds Vim-style selection and text objects to **native tmux copy mode**, without opening a separate viewer. It keeps the tmux buffer and existing copy-mode navigation and search, and requires only the Python 3 standard library.

Requires Python 3.9+ and tmux 3.7+. The plugin needs `capture-pane -M` / `-F` support to preserve copy-mode snapshots and line-wrapping information, and checks for these features during installation. The shell entry point is compatible with the default Bash 3.2 on macOS.

## Installation

### TPM

Add the plugin declaration before the TPM initialization line, then press `prefix + I` to install.

```tmux
set -g @plugin 'clang-engineer/tmux-vim-copy'
```

If you also use tmux-open, declare this plugin after tmux-open. Installation sets
`mode-keys` to `vi` and overrides only the required keys; it does not reset the entire existing key table.

### Manual installation and local development

```sh
git clone https://github.com/clang-engineer/tmux-vim-copy ~/.tmux/plugins/tmux-vim-copy
```

Add the following to `~/.tmux.conf` and reload the configuration.

```tmux
run-shell '~/.tmux/plugins/tmux-vim-copy/vim-copy.tmux'
```

From a running tmux session, you can also execute the entry point directly from your checkout.

```sh
bash /absolute/path/to/tmux-vim-copy/vim-copy.tmux
```

## Keys

Enter copy mode with the standard tmux binding, prefix + `[`.

| Key | Action |
| --- | --- |
| `v` / `V` / `Ctrl-v` | Characterwise / linewise / rectangular selection |
| `y` | Copy the selection; without a selection, use `yy` to copy the current line |
| `O` | Swap the selection endpoints |
| `iw` / `aw`, `iW` / `aW` | Select inside / around a word or whitespace-delimited WORD |
| `ip` / `ap` | Select inside / around a paragraph |
| `i"`, `i'`, `` i` `` and the corresponding `a` combinations | Select inside / around quotes, with escape handling |
| `i(`, `i{`, `i[`, `i<` and the corresponding `a` combinations | Select inside / around nested, multiline brackets |
| `ib` / `ab`, `iB` / `aB` | Aliases for `()` and `{}`, respectively |
| `i)`, `i}`, `i]`, `i>` and the corresponding `a` combinations | Closing bracket keys select the same objects |
| `gg` / `ge` / `gE` | Go to the start of the buffer / end of the previous word / end of the previous WORD |
| `zt` / `zz` / `zb` | Position the cursor line at the top / center / bottom of the screen |

While waiting for a second key after `i`/`a`/`g`/`z`, or the first `y` without a selection, press `Escape`, `Ctrl-c`, `q`, or an unsupported key to cancel without leaving copy mode. Empty or unmatched objects display a message without changing the cursor or existing selection.

Existing tmux word motions, search, and numeric counts remain unchanged. For example, `3w` retains its native tmux behavior. Numeric prefixes for the new Python-backed actions, such as `3iw`, are not supported.

`g` and `z` become prefixes that wait for a second key. Use `gg` for tmux's original single-key `g` action, and `zz` for its original single-key `z` action. In characterwise, linewise, or blockwise mode, pressing the same selection key again clears the selection without leaving copy mode.

## Options

Set these before installing or reloading the plugin.

```tmux
set -g @vim-copy-yank-exit 'on'
set -g @vim-copy-swap-key 'O'
set -g @vim-copy-python 'python3'
```

- `@vim-copy-yank-exit`: defaults to `on`, which exits copy mode after copying. Set it to `off` to keep the selection and remain in copy mode after copying.
- `@vim-copy-swap-key`: the key for swapping selection endpoints; defaults to `O`. Choosing another key may override its existing binding.
- `@vim-copy-python`: a Python executable name or absolute path, without arguments. During installation, the `TMUX_VIM_COPY_PYTHON` environment variable takes precedence over this option. If neither is set, the plugin uses `python3`.

```sh
TMUX_VIM_COPY_PYTHON=/absolute/path/to/python3 bash /absolute/path/to/tmux-vim-copy/vim-copy.tmux
```

The default swap key is uppercase `O`, so it does not take over tmux-open's `o`, `Ctrl-o`, or `S`. You keep the existing copy-mode UI and tmux-open integration; no separate viewer is launched.

## Limitations and safety

- Text objects operate on the text held by tmux. This is not a parser for programming-language comments, strings, or syntax. In complex code, it may select a different bracket or quote pair than you expect.
- Quote objects are limited to one logical line. Bracket objects support nesting and multiple lines, and terminal-wrapped lines are rejoined into their logical source lines. Word boundaries distinguish Unicode letters, numbers, underscores, and combining marks from punctuation; WORDs are separated by whitespace. The plugin does not import Vim's `iskeyword` setting.
- Cell coordinates account for full-width CJK characters and combining marks. Helper-based selection is explicitly rejected on lines containing complex emoji sequences, such as ZWJ, variation selectors, skin-tone modifiers, or flag sequences, leaving the existing selection unchanged. Use native tmux navigation and selection on those lines.
- `ip` selects a paragraph linewise, excluding the surrounding blank lines. `ap` includes trailing blank lines, or leading blank lines if there are none after the paragraph. Empty inner objects and unmatched brackets do not result in an incorrect selection.
- Install only code and Python executables you trust. This plugin does not interpolate selected text into shell commands or execute it. Execution behavior in other plugins, such as tmux-open, follows those plugins' policies.
- Copying uses the tmux buffer. System clipboard integration depends on your existing tmux configuration.

## Development and references

```sh
make test
make lint
```

`make test` runs the standard-library `unittest` suite. `make lint` compiles Python source to check syntax without external tools or writing bytecode files.

The project's current local verification environment is macOS, tmux 3.7c, and Python 3.15. Verification covers pure text-object tests and real tmux client tests using an isolated socket. Linux and macOS CI configurations are also included; local verification is not presented as evidence that CI has passed.

References for behavior and visual selection state: [pwnalone/tmux-vi-copy-mode](https://github.com/pwnalone/tmux-vi-copy-mode) and [shitcoding/tmux_yankee](https://github.com/shitcoding/tmux_yankee) (both MIT). This project is an independent implementation, not a fork of either project, and does not copy their code.

MIT License. Copyright (c) 2026 clang-engineer.
