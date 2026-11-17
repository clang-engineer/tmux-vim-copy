"""Real tmux client tests: no mocked key bindings or selection forwarding."""
import errno
import fcntl
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import struct
import tempfile
import termios
import threading
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("tmux"), "tmux is required for integration tests")
class NativeCopyMode(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="vim-copy-test-")
        self.socket = str(Path(self.directory.name) / "socket")
        self.pane = "test:0.0"
        self.client_process = None
        self.terminal = None
        self.output = b""
        self.rendered = threading.Condition()
        self.reader = None
        self.addCleanup(self.close)
        self.command("-f", "/dev/null", "new-session", "-d", "-s", "test",
                     "-x", "80", "-y", "16", "sh")
        self.command("set-option", "-s", "escape-time", "0")
        self.command("set-option", "-g", "status", "off")
        self.command("set-option", "-s", "set-clipboard", "off")
        self.command("set-option", "-g", "@vim-copy-python", sys.executable)
        attached = "attached-" + uuid.uuid4().hex
        self.terminal, slave = os.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 16, 80, 0, 0))
        try:
            self.client_process = subprocess.Popen(
                ["tmux", "-S", self.socket, "attach-session", "-t", "test",
                 ";", "wait-for", "-S", attached],
                stdin=slave, stdout=slave, stderr=slave,
                env={**os.environ, "TERM": "xterm-256color"},
            )
        finally:
            os.close(slave)
        self.reader = threading.Thread(target=self.drain_terminal, daemon=True)
        self.reader.start()
        self.wait(attached)
        self.client = self.command("list-clients", "-F", "#{client_name}").strip()
        self.install()

    def close(self):
        subprocess.run(["tmux", "-S", self.socket, "kill-server"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if self.client_process:
            self.client_process.wait(timeout=5)
        if self.reader:
            self.reader.join(timeout=5)
        if self.terminal is not None:
            os.close(self.terminal)
        self.directory.cleanup()

    def drain_terminal(self):
        try:
            while True:
                data = os.read(self.terminal, 65536)
                if not data:
                    break
                with self.rendered:
                    self.output = (self.output + data)[-8192:]
                    self.rendered.notify_all()
        except OSError as error:
            if error.errno != errno.EIO:  # PTY slave closed when tmux detached.
                raise

    def command(self, *args):
        result = subprocess.run(["tmux", "-S", self.socket, *args],
                                text=True, capture_output=True, timeout=15)
        if result.returncode:
            self.fail(result.stderr.strip() or repr(args))
        return result.stdout if args[0] == "show-buffer" else result.stdout.rstrip("\n")

    def wait(self, name):
        self.command("wait-for", name)

    def install(self):
        self.command("run-shell", "bash " + shlex.quote(str(ROOT / "vim-copy.tmux")))

    def field(self, name):
        return self.command("display-message", "-p", "-t", self.pane, "#{" + name + "}")

    def fixture(self, text, row=0, column=0):
        if self.field("pane_in_mode") == "1":
            self.command("send-keys", "-t", self.pane, "-X", "cancel")
        self.command("clear-history", "-t", self.pane)
        ready = "fixture-" + uuid.uuid4().hex
        script = "printf '%s\\n' " + shlex.quote(text)
        script += "; tmux wait-for -S " + ready + "; exec sh"
        self.command("respawn-pane", "-k", "-t", self.pane, script)
        self.wait(ready)
        self.command("copy-mode", "-t", self.pane)
        self.command("send-keys", "-t", self.pane, "-X", "history-top")
        self.command("send-keys", "-t", self.pane, "-X", "start-of-line")
        if row:
            self.command("send-keys", "-t", self.pane, "-X", "-N", str(row), "cursor-down")
        if column:
            self.command("send-keys", "-t", self.pane, "-X", "-N", str(column), "cursor-right")

    def keys(self, *keys):
        # The barrier follows real client key processing, including synchronous
        # run-shell jobs, and works whether y has exited Copy Mode or not.
        ready = "keys-" + uuid.uuid4().hex
        for table in ("copy-mode-vi", "root"):
            self.command("bind-key", "-T", table, "F12", "wait-for", "-S", ready)
        self.command("send-keys", "-K", "-c", self.client, *keys, "F12")
        self.wait(ready)

    def copied(self):
        self.assertTrue(self.field("selection_present") == "1"
                        or self.field("selection_active") == "1")
        self.command("send-keys", "-t", self.pane, "-X", "copy-selection-no-clear")
        return self.command("show-buffer")

    def test_visual_toggle_and_character_block_line_transitions(self):
        self.fixture("alpha beta\nsecond line", column=2)
        self.keys("v", "l", "l")
        self.assertEqual(self.copied(), "pha")
        self.keys("C-v")
        self.assertEqual(self.field("rectangle_toggle"), "1")
        self.assertEqual(self.copied(), "pha")
        self.keys("V")
        self.assertEqual(self.field("selection_mode"), "line")
        self.assertEqual(self.copied(), "alpha beta\n")
        self.keys("v")
        self.assertEqual(self.copied(), "pha")
        self.keys("v")
        self.assertEqual(self.field("selection_present"), "0")
        self.assertEqual(self.field("pane_in_mode"), "1")

    def test_multiline_visual_line_transition_preserves_character_endpoints(self):
        self.fixture("alpha beta\nsecond line", column=2)
        self.keys("v", "j", "l", "l", "V")
        self.assertEqual(self.copied(), "alpha beta\nsecond line\n")
        self.keys("v")
        self.assertEqual(self.copied(), "pha beta\nsecon")

    def test_complex_emoji_does_not_corrupt_an_existing_selection(self):
        self.fixture("word 👩‍💻 tail", column=0)
        self.command("send-keys", "-t", self.pane, "-X", "begin-selection")
        self.command("send-keys", "-t", self.pane, "-X", "cursor-right")
        original = self.copied()
        self.keys("i", "w")
        self.assertEqual(self.copied(), original)
        self.assertEqual(self.field("pane_in_mode"), "1")

    def test_block_selection_spans_columns_and_toggles_off(self):
        self.fixture("abcde\nfghij", column=1)
        self.keys("C-v", "j", "l", "l")
        self.assertEqual(self.copied(), "bcd\nghi")
        self.keys("C-v")
        self.assertEqual(self.field("selection_present"), "0")
        self.assertEqual(self.field("rectangle_toggle"), "0")

    def test_nested_multiline_objects_and_delimiter_cursor(self):
        text = "prefix (outer\n  [other (inner) item]\n tail) suffix"
        self.fixture(text, row=1, column=11)
        self.keys("v", "i", "b")
        self.assertEqual(self.copied(), "inner")
        self.fixture(text, column=7)
        self.keys("v", "i", "b")
        self.assertEqual(self.copied(), "outer\n  [other (inner) item]\n tail")
        self.fixture(text, row=1, column=4)
        self.keys("v", "a", "]")
        self.assertEqual(self.copied(), "[other (inner) item]")

    def test_escaped_quotes_and_empty_objects_preserve_original_selection(self):
        self.fixture(r'prefix "one\"two" suffix', column=10)
        self.keys("v", "i", '"')
        self.assertEqual(self.copied(), r'one\"two')
        self.fixture('x () "" y', column=2)
        self.keys("v")
        before = (self.field("copy_cursor_x"), self.copied())
        self.keys("i", "b")
        self.assertEqual((self.field("copy_cursor_x"), self.copied()), before)
        self.fixture("x (unclosed y", column=5)
        self.keys("v", "l")
        before = self.copied()
        self.keys("i", "b")
        self.assertEqual(self.copied(), before)

    def test_soft_wraps_are_not_inserted_into_word_or_bracket_objects(self):
        word = "a" * 95
        self.fixture("x (" + word + ") y", row=1, column=4)
        self.keys("v", "i", "b")
        self.assertEqual(self.copied(), word)
        self.fixture(word + " next", row=1, column=3)
        self.keys("v", "i", "w")
        self.assertEqual(self.copied(), word)

    def test_unicode_cells_and_decomposed_accents_select_complete_words(self):
        self.fixture("앞 (한글 café) 뒤", column=7)
        self.keys("v", "i", "b")
        self.assertEqual(self.copied(), "한글 café")
        self.fixture("prefix e\u0301lan suffix", column=9)
        self.keys("v", "i", "w")
        self.assertEqual(self.copied(), "e\u0301lan")

    def test_around_words_and_paragraph_separators(self):
        self.fixture("one two three", column=5)
        self.keys("v", "a", "w")
        self.assertEqual(self.copied(), "two ")
        self.fixture("first\nsecond\n\nlast", row=1, column=2)
        self.keys("v", "i", "p")
        self.assertEqual(self.copied(), "first\nsecond\n")
        self.keys("a", "p")
        self.assertEqual(self.copied(), "first\nsecond\n\n")

    def test_pending_prefixes_cancel_without_losing_selection(self):
        for prefix in ("i", "a", "g", "z"):
            for cancel in ("Escape", "C-c", "q", "!"):
                with self.subTest(prefix=prefix, cancel=cancel):
                    self.fixture("alpha beta", column=2)
                    self.keys("v", prefix, cancel)
                    self.assertEqual(self.field("pane_in_mode"), "1")
                    self.assertEqual(self.copied(), "p")

    def test_yank_exit_policy_and_double_y_current_line(self):
        self.fixture("first\nsecond\nthird", row=1, column=3)
        self.keys("y", "y")
        self.assertEqual(self.field("pane_in_mode"), "0")
        self.assertEqual(self.command("show-buffer"), "second\n")
        self.command("set-option", "-g", "@vim-copy-yank-exit", "off")
        self.fixture("alpha beta", column=1)
        self.keys("v", "l", "y")
        self.assertEqual(self.field("pane_in_mode"), "1")
        self.assertEqual(self.field("selection_present"), "1")
        self.assertEqual(self.command("show-buffer"), "lp")
        self.keys("v")
        self.keys("y", "Escape")
        self.assertEqual(self.field("pane_in_mode"), "1")
        self.assertEqual(self.field("selection_present"), "0")

    def test_other_end_and_reload_with_changed_swap_key(self):
        self.fixture("alpha beta", column=1)
        self.keys("v", "l", "l", "O")
        self.assertEqual(self.field("copy_cursor_x"), "1")
        self.assertEqual(self.copied(), "lph")
        self.command("set-option", "-g", "@vim-copy-swap-key", "M-o")
        self.install()
        self.keys("M-o")
        self.assertEqual(self.field("copy_cursor_x"), "3")
        self.assertEqual(self.copied(), "lph")
        self.keys("O")
        self.assertEqual(self.field("copy_cursor_x"), "3")

    def test_previous_word_end_first_line_and_native_count_motions(self):
        self.fixture("zero one,two three four", column=15)
        self.keys("g", "e")
        self.assertEqual(self.field("copy_cursor_x"), "11")
        self.keys("g", "E")
        self.assertEqual(self.field("copy_cursor_x"), "3")
        self.fixture("one two three four", column=6)
        self.keys("g", "g")
        # Native digit bindings open a prompt. A control-mode client cannot
        # model its input, and batching 3w can precede prompt installation.
        bindings = (shlex.split(line) for line in
                    self.command("list-keys", "-T", "copy-mode-vi").splitlines())
        digit = next(parts for parts in bindings if parts[3] == "3")
        prompt = digit[digit.index("-p") + 1].encode()
        with self.rendered:
            self.output = b""
            os.write(self.terminal, b"3")
            self.assertTrue(self.rendered.wait_for(lambda: prompt in self.output, timeout=5))
        self.keys("w")
        self.assertEqual(self.field("copy_cursor_x"), "14")

    def test_viewport_is_preserved_by_visual_selection_and_positioned_by_z(self):
        lines = "\n".join("row-%02d" % i for i in range(40))
        self.fixture(lines, row=25, column=2)
        before = self.field("scroll_position")
        self.keys("v")
        self.assertEqual(self.field("scroll_position"), before)
        self.keys("z", "t")
        self.assertEqual(self.field("copy_cursor_y"), "0")
        self.keys("z", "b")
        self.assertEqual(self.field("copy_cursor_y"), "15")
        self.keys("z", "z")
        self.assertIn(int(self.field("copy_cursor_y")), (7, 8))

    def test_copy_snapshot_is_not_replaced_by_new_output(self):
        self.fixture("before (frozen) after", column=10)
        # Independent output arrives while the original Copy Mode grid remains
        # frozen. Text objects must resolve against that original grid.
        self.command("run-shell", "printf 'new output\\n' > " + shlex.quote(self.field("pane_tty")))
        self.keys("v", "i", "b")
        self.assertEqual(self.copied(), "frozen")


if __name__ == "__main__":
    unittest.main()
