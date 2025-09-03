> **Note**: This document explains the PowerShell one-liner approach for directly passing system prompts. For a more robust solution that handles additional flags like `--settings` and works consistently across all Windows shells, see [SHARED_POSIX_SCRIPT_APPROACH.md](SHARED_POSIX_SCRIPT_APPROACH.md).

Here is a precise, end-to-end explanation of what every character in your working line does, why earlier attempts failed, and why this one succeeds.

```powershell
& 'C:\Program Files\Git\bin\bash.exe' --% -lc 'p=$(tr -d "\r" < ~/.claude/prompts/python-developer.md); exec claude --append-system-prompt="$p"'
```

## Stage 1, PowerShell launches Git Bash

1. `&` is PowerShell’s call operator. It tells PowerShell to execute the following string as a program path, even if the string contains spaces. Without `&`, a quoted path would be treated as a plain string, not executed. ([Microsoft Learn][1], [SS64][2])

2. `'C:\Program Files\Git\bin\bash.exe'` is the full path to the Git Bash executable. Quoting the path prevents PowerShell from splitting on spaces.

3. `--%` is the PowerShell stop-parsing token. Everything after `--%` on this line is passed to the native program exactly as typed. PowerShell does not expand `$`, does not interpret `$(...)`, does not treat `"` specially, and does not try to re-tokenize anything. This is the key to avoiding the quoting chaos you were seeing. ([Microsoft Learn][3])

PowerShell therefore runs:

* program: `C:\Program Files\Git\bin\bash.exe`
* arguments, passed verbatim: `-lc 'p=$(tr -d "\r" < ~/.claude/prompts/python-developer.md); exec claude --append-system-prompt="$p"'`

## Stage 2, Bash interprets `-lc '…'`

4. `-l` tells Bash to behave as a login shell. That mainly affects which startup files it reads. It is not essential here, but it is harmless. ([Ask Ubuntu][4])

5. `-c '…'` tells Bash to execute the following command string and then exit. The single quotes here are parsed by Bash, not by PowerShell, because `--%` prevented PowerShell from touching them. ([GNU][5])

So inside Bash, the command string to run is:

```bash
p=$(tr -d "\r" < ~/.claude/prompts/python-developer.md); exec claude --append-system-prompt="$p"
```

## Stage 3, inside Bash, build the argument value

6. `~/.claude/prompts/python-developer.md` uses tilde expansion. In Bash, `~` expands to the current user’s home directory. In Git Bash on Windows the home directory maps to your Windows user profile, for example `/c/Users/Aleksandr`. ([GNU][6], [msys2.org][7])

7. `< file` is input redirection. It feeds the file contents to the left-hand command’s standard input. Here it feeds the file to `tr`. ([GNU][8])

8. `tr -d "\r"` deletes carriage return characters. Windows text files often have CRLF line endings, that is `\r\n`. Removing `\r` leaves clean LF only, which avoids odd parsing errors that can happen when CR characters sneak into quoted strings or command substitutions. ([man7.org][9])

9. `$( … )` is command substitution. Bash runs the command inside the parentheses in a subshell, captures its standard output, strips trailing newlines, and substitutes the result. The result becomes the value assigned to the variable `p`. Embedded newlines are preserved, so the full multi-line file ends up in `p`. ([GNU][10])

After this step, `p` holds the entire prompt file as a single string, with `\r` removed and `\n` intact.

## Stage 4, call the CLI correctly and hand it one argument

10. `exec claude --append-system-prompt="$p"` runs the `claude` program and replaces the current Bash process with it. Using `exec` avoids keeping an extra shell process around, so the interactive session is owned by the CLI. This is conventional when you use a shell wrapper to launch an interactive program. ([man7.org][11])

11. `"${p}"` is double-quoted. Quoting is crucial. In Bash, double quotes prevent word splitting and filename globbing, so the entire multi-line value is passed as a single argument to `--append-system-prompt`. Newlines inside the quotes are preserved and travel as data. Without the quotes, the shell would split on whitespace, which would fragment your prompt into many arguments. ([GNU][12])

12. Why this avoids the infamous `unknown option '---'` error: many system-prompt files start with front-matter like `---`. In your failed attempts, the program wrapper on Windows was mis-tokenizing the multi-line value, so a line starting with dashes was getting interpreted as a new option. In this working form, Bash passes exactly two argv entries to `claude`: the flag name `--append-system-prompt`, then one single argument that contains the entire file. Since the parser sees the flag already, it treats the next token as its value, even if the value begins with a dash. Quoting prevents any intermediate splitting that could have created extra tokens. The behaviour that double quotes stop word splitting is specified in the Bash manual under Word Splitting. ([GNU][12])

## Why the PowerShell, CMD, and mixed-shell attempts failed

* PowerShell by default parses and expands `$`, `$(…)`, quotes, and backticks. When you try to embed a Bash command substitution inside a PowerShell string, you create two different quoting layers that both want to process `$` and quotes. That is why `--%` was necessary, it stops PowerShell from interpreting the rest of the line and lets Bash be the only parser. ([Microsoft Learn][3])

* The `claude.cmd` or `claude.ps1` shims on Windows are not friendly to very long, multi-line arguments. The legacy `cmd.exe` command line length limit and argument handling make this especially brittle, which is why you saw errors like “Too long command line” or spurious option parsing. Launching the real Bash first, then `exec`-ing the CLI from Bash, avoids those layers and their limitations. Microsoft documents the stop-parsing token for exactly these scenarios, where you must pass complex arguments to a native tool without PowerShell interference. ([Microsoft Learn][3])

## Micro-timeline of what happens

1. PowerShell uses `&` to start `bash.exe`. It stops parsing at `--%`, so it forwards `-lc '…'` verbatim. ([Microsoft Learn][1])
2. Bash starts as a login shell because of `-l`, then executes the command string because of `-c`. ([GNU][5])
3. Bash expands `~` to your home, opens the file with `<`, runs `tr -d '\r'`, captures the result with `$( … )`, and assigns it to `p`. ([GNU][6], [man7.org][9])
4. Bash runs `exec claude --append-system-prompt="$p"`. `exec` replaces the shell process with the Claude CLI. The quoted `$p` travels as a single argument that contains the entire multi-line prompt. ([man7.org][11], [GNU][12])

That is why your exact line is reliable: one shell parses once, you normalize line endings, you quote the value so it is one argument, and you avoid Windows shims that mangle long multi-line parameters.

[1]: https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_operators?view=powershell-7.5&utm_source=chatgpt.com "about_Operators - PowerShell"
[2]: https://ss64.com/ps/call.html?utm_source=chatgpt.com "Call operator - Run - PowerShell"
[3]: https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_parsing?view=powershell-7.5&utm_source=chatgpt.com "about_Parsing - PowerShell"
[4]: https://askubuntu.com/questions/463462/sequence-of-scripts-sourced-upon-login?utm_source=chatgpt.com "Sequence of scripts sourced upon login"
[5]: https://www.gnu.org/s/bash/manual/html_node/Invoking-Bash.html?utm_source=chatgpt.com "Invoking Bash (Bash Reference Manual)"
[6]: https://www.gnu.org/s/bash/manual/html_node/Tilde-Expansion.html?utm_source=chatgpt.com "Tilde Expansion (Bash Reference Manual)"
[7]: https://www.msys2.org/docs/filesystem-paths/?utm_source=chatgpt.com "Filesystem Paths"
[8]: https://www.gnu.org/s/bash/manual/html_node/Redirections.html?utm_source=chatgpt.com "Redirections (Bash Reference Manual)"
[9]: https://man7.org/linux/man-pages/man1/tr.1.html?utm_source=chatgpt.com "tr(1) - Linux manual page"
[10]: https://www.gnu.org/s/bash/manual/html_node/Command-Substitution.html?utm_source=chatgpt.com "Command Substitution (Bash Reference Manual)"
[11]: https://man7.org/linux/man-pages/man1/exec.1p.html?utm_source=chatgpt.com "exec(1p) - Linux manual page"
[12]: https://www.gnu.org/s/bash/manual/html_node/Word-Splitting.html?utm_source=chatgpt.com "Word Splitting (Bash Reference Manual)"
