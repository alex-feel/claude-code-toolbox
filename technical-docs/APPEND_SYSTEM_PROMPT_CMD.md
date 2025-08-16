Here is a precise, end-to-end explanation of why the **CMD** one-liner works and what each part does:

```cmd
"C:\Program Files\Git\bin\bash.exe" -lc "p=$(tr -d '\r' < ~/.claude/prompts/python-developer.md); exec claude --append-system-prompt=\"$p\""
```

# 1) What CMD contributes

* **`"C:\Program Files\Git\bin\bash.exe"`**
  In `cmd.exe`, double quotes group a path with spaces into a single token, so the program launched is Git Bash. Inside a quoted argument for a Windows program, backslash-quote `\"` is the standard way to embed a literal double quote in the same argument, per the Microsoft C runtime command-line parsing rules that most Windows programs use. ([Microsoft Learn][1])

* **Everything after that becomes arguments to `bash.exe`**
  `-l` asks Bash to run as a login shell, and `-c "…"` tells Bash to execute the given command string. CMD passes that entire string as one argument because it is wrapped in double quotes. Also note that characters like `&` and `|` are special in CMD, which is why wrapping the `-c` payload in quotes is required to avoid CMD’s own metacharacter parsing. ([Microsoft Learn][2])

* **Command-line length caveat**
  CMD itself imposes about **8191** characters as the maximum command-line length. Your line stays far under that, so it executes reliably, but it is a useful limit to remember when you embed long data. The underlying Win32 `CreateProcess` API allows up to **32767** characters, however when you invoke via CMD you are bound by CMD’s lower limit. ([Microsoft Learn][3], [Microsoft for Developers][4])

# 2) What Bash does with `-lc "…"`

The string given to `-c` is parsed by Bash, not by CMD. Inside that string:

* **`~/.claude/prompts/python-developer.md`**
  Tilde expansion happens in Bash, `~` becomes the current user’s home. In Git Bash, home maps to your Windows profile directory and POSIX-style drive prefixing is used, for example `/c/Users/<name>`. ([GNU][5], [MSYS2][6])

* **`< file` input redirection**
  The `<` operator redirects the named file to the standard input of the command on its left. Here it feeds the prompt file into `tr`. ([GNU][7])

* **`tr -d '\r'`**
  `tr` is run from GNU coreutils. With `-d`, `tr` deletes every occurrence of the characters listed, so `'\r'` strips Windows carriage returns, leaving clean LF line endings. That prevents odd parsing issues when multi-line text later becomes a single shell argument. ([GNU][8])

* **`p=$( … )` command substitution**
  `$( … )` runs the command and substitutes its standard output. Bash captures all bytes from `tr` and assigns them to the variable `p`. Trailing newlines are removed, embedded newlines are preserved, which is exactly what you want for a multi-line system prompt. ([GNU][9])

* **`exec claude --append-system-prompt="$p"`**
  `exec` replaces the current Bash process with the `claude` CLI, so you do not keep an extra shell in the foreground. The value expansion is **double-quoted**, which is the critical part. In Bash, double quotes suppress word splitting and globbing, so the entire multi-line value in `p` is passed to `--append-system-prompt` as one argument, even if the first line begins with `---`. This avoids the classic “unknown option '---'” failure that happens when a multi-line value is accidentally split into separate argv tokens. ([GNU][10])

# 3) Why this pattern succeeds where others fail

* **CMD’s quoting and metacharacters are tricky**
  Without the outer double quotes, CMD would try to interpret `&`, `|`, `(`, and `)` in your Bash payload, which would corrupt the command. Quoting once at the CMD layer hands one opaque argument to `bash.exe`, and all further parsing is done by Bash, which is what you want here. ([Microsoft Learn][2])

* **The value is bound to the flag as a single argv element**
  The combination of Bash variable assignment, quoting, and `exec` ensures `claude` receives exactly two things for this feature, the flag name and one value string. Because the value is already the next argv item, the CLI parser treats it as data, not as another option, even if its first characters are `---`. The “single argument” property comes from Bash’s word-splitting rules, which say that expansions enclosed in double quotes are not split. ([GNU][11])

* **CRLF normalization prevents stray `\r` from leaking**
  CR characters in Windows-created files can sneak into an argument and confuse downstream parsers. Removing `\r` with `tr -d '\r'` is a simple, POSIX-friendly way to normalize the text before it becomes an argument. ([GNU][8])

# 4) Micro-timeline of execution

1. `cmd.exe` launches `bash.exe` with `-lc "<payload>"`. The quotes make the payload one argument, and embedded `\"` sequences survive as literal quotes inside that argument per the CRT argument rules. ([Microsoft Learn][1])
2. Bash, as a login shell due to `-l`, executes the `-c` string. It expands `~`, redirects the file into `tr`, deletes `\r`, and captures the result in `p` via command substitution. ([GNU][5])
3. Bash runs `exec claude --append-system-prompt="$p"`. Because `$p` is double-quoted, it is passed as one multi-line value. The shell process is replaced by the CLI, so the terminal is attached directly to `claude`. ([GNU][10])

That is the complete mechanics behind your working CMD line.

[1]: https://learn.microsoft.com/en-us/cpp/c-language/parsing-c-command-line-arguments?view=msvc-170&utm_source=chatgpt.com "Parsing C command-line arguments"
[2]: https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/cmd?utm_source=chatgpt.com "cmd"
[3]: https://learn.microsoft.com/en-us/troubleshoot/windows-client/shell-experience/command-line-string-limitation?utm_source=chatgpt.com "Command prompt line string limitation - Windows Client"
[4]: https://devblogs.microsoft.com/oldnewthing/20031210-00/?p=41553&utm_source=chatgpt.com "What is the command line length limit? - The Old New Thing"
[5]: https://www.gnu.org/s/bash/manual/html_node/Tilde-Expansion.html?utm_source=chatgpt.com "Tilde Expansion (Bash Reference Manual)"
[6]: https://www.msys2.org/docs/filesystem-paths/?utm_source=chatgpt.com "Filesystem Paths"
[7]: https://www.gnu.org/s/bash/manual/html_node/Redirections.html?utm_source=chatgpt.com "Redirections (Bash Reference Manual)"
[8]: https://www.gnu.org/software/coreutils/manual/html_node/index.html?utm_source=chatgpt.com "Top (GNU Coreutils 9.7)"
[9]: https://www.gnu.org/s/bash/manual/html_node/Command-Substitution.html?utm_source=chatgpt.com "Command Substitution (Bash Reference Manual)"
[10]: https://www.gnu.org/software/bash/manual/html_node/Shell-Builtin-Commands.html?utm_source=chatgpt.com "Shell Builtin Commands (Bash Reference Manual)"
[11]: https://www.gnu.org/software/bash/manual/html_node/Word-Splitting.html?utm_source=chatgpt.com "Word Splitting (Bash Reference Manual)"
