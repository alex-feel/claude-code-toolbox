# Changelog

## [4.24.4](https://github.com/alex-feel/claude-code-toolbox/compare/v4.24.3...v4.24.4) (2026-01-22)


### Bug Fixes

* ensure profile-only MCP servers trigger removal from all scopes ([2b80428](https://github.com/alex-feel/claude-code-toolbox/commit/2b8042875eaaefa8cec31be0b1013607752b53b3))

## [4.24.3](https://github.com/alex-feel/claude-code-toolbox/compare/v4.24.2...v4.24.3) (2026-01-22)


### Bug Fixes

* resolve MCP server removal and display format bugs ([b18cc6a](https://github.com/alex-feel/claude-code-toolbox/commit/b18cc6ae59684b053ad5cfc8d859567110549726))

## [4.24.2](https://github.com/alex-feel/claude-code-toolbox/compare/v4.24.1...v4.24.2) (2026-01-22)


### Bug Fixes

* resolve MCP server configuration bugs on Windows ([b09ab7b](https://github.com/alex-feel/claude-code-toolbox/commit/b09ab7bb4829a930b930e545b3a6ce793179e43d))

## [4.24.1](https://github.com/alex-feel/claude-code-toolbox/compare/v4.24.0...v4.24.1) (2026-01-22)


### Bug Fixes

* prevent MSYS path conversion in run_bash_command ([e62da7c](https://github.com/alex-feel/claude-code-toolbox/commit/e62da7cbd25631d1177513fc8c247fb20ab82884))

## [4.24.0](https://github.com/alex-feel/claude-code-toolbox/compare/v4.23.1...v4.24.0) (2026-01-22)


### Features

* add combined scope support for MCP servers ([9c01263](https://github.com/alex-feel/claude-code-toolbox/commit/9c01263183ad6c80cca819cc2b1e375d95860df7))


### Bug Fixes

* parse MCP profile config commands correctly ([b51cd4c](https://github.com/alex-feel/claude-code-toolbox/commit/b51cd4c7965fc5daebd53824c955d97684c2d62a))

## [4.23.1](https://github.com/alex-feel/claude-code-toolbox/compare/v4.23.0...v4.23.1) (2026-01-21)


### Bug Fixes

* ensure profile MCP servers removed from all scopes before configuration ([44cb5ba](https://github.com/alex-feel/claude-code-toolbox/commit/44cb5ba6a1b9bb48a4d3e3715f3a0aebb5e4485a))

## [4.23.0](https://github.com/alex-feel/claude-code-toolbox/compare/v4.22.1...v4.23.0) (2026-01-21)


### Features

* add MCP server profile scope isolation ([503c5d7](https://github.com/alex-feel/claude-code-toolbox/commit/503c5d7e0bb17b578c758411ce1472a57ec89cb6))

## [4.22.1](https://github.com/alex-feel/claude-code-toolbox/compare/v4.22.0...v4.22.1) (2026-01-21)


### Bug Fixes

* update installMethod config after native Claude installation ([d73ca5a](https://github.com/alex-feel/claude-code-toolbox/commit/d73ca5ae5cff6ad15361acedeae5b3f23933fe9b))

## [4.22.0](https://github.com/alex-feel/claude-code-toolbox/compare/v4.21.4...v4.22.0) (2026-01-20)


### Features

* add automatic npm Claude removal after native installation ([830e536](https://github.com/alex-feel/claude-code-toolbox/commit/830e536e20f46bf6157ae90fe15957a33afa0b8a))

## [4.21.4](https://github.com/alex-feel/claude-code-toolbox/compare/v4.21.3...v4.21.4) (2026-01-20)


### Bug Fixes

* detect native Claude installations in .local/bin on macOS/Linux ([70690a7](https://github.com/alex-feel/claude-code-toolbox/commit/70690a71e569fd97b30a25c94f855e7677b8f89e))
* download both Python scripts in bootstrap for module imports ([3e333af](https://github.com/alex-feel/claude-code-toolbox/commit/3e333afe56c22df150dfe13382445791863c0c46))

## [4.21.3](https://github.com/alex-feel/claude-code-toolbox/compare/v4.21.2...v4.21.3) (2026-01-20)


### Bug Fixes

* prevent auto-update when installing specific Claude Code versions ([beab951](https://github.com/alex-feel/claude-code-toolbox/commit/beab951e596225a3443da1c444be9ec9125606cb))

## [4.21.2](https://github.com/alex-feel/claude-code-toolbox/compare/v4.21.1...v4.21.2) (2026-01-19)


### Bug Fixes

* handle Windows file locking when Claude Code is running during installation ([ad12d19](https://github.com/alex-feel/claude-code-toolbox/commit/ad12d19fc1a0978c9cebcc68e8f79cc4a971588a))
* resolve MyPy unreachable code errors in Windows-specific functions ([893105b](https://github.com/alex-feel/claude-code-toolbox/commit/893105b6f8e3213bea0976dc9512e30bac872903))

## [4.21.1](https://github.com/alex-feel/claude-code-toolbox/compare/v4.21.0...v4.21.1) (2026-01-19)


### Bug Fixes

* implement direct GCS download to bypass Anthropic installer version bug ([183b9ee](https://github.com/alex-feel/claude-code-toolbox/commit/183b9eed006a4b947977dd2e6cca02b554a67a8c))

## [4.21.0](https://github.com/alex-feel/claude-code-toolbox/compare/v4.20.0...v4.21.0) (2026-01-19)


### Features

* add HTTP 429 rate limiting with exponential backoff for parallel downloads ([1e3e08b](https://github.com/alex-feel/claude-code-toolbox/commit/1e3e08bfbd43af6c431b37fe4928fd430d8c838c))

## [4.20.0](https://github.com/alex-feel/claude-code-toolbox/compare/v4.19.1...v4.20.0) (2026-01-19)


### Features

* add GitHub API rate limiting with authentication and retry logic ([4f28c76](https://github.com/alex-feel/claude-code-toolbox/commit/4f28c76ed9f47baeca0ffae816f3f9c8ee13c7a0))

## [4.19.1](https://github.com/alex-feel/claude-code-toolbox/compare/v4.19.0...v4.19.1) (2026-01-19)


### Bug Fixes

* remove token message spam and parallelize skills processing ([49b3ad7](https://github.com/alex-feel/claude-code-toolbox/commit/49b3ad7c518ab129bb4009122bf431f67f6c5136))

## [4.19.0](https://github.com/alex-feel/claude-code-toolbox/compare/v4.18.6...v4.19.0) (2026-01-19)


### Features

* add parallel execution for remote file operations ([bad8fe7](https://github.com/alex-feel/claude-code-toolbox/commit/bad8fe735667dba7550a4659089c0645b43b61f4))


### Bug Fixes

* improve summary with skills command ([2f9a18b](https://github.com/alex-feel/claude-code-toolbox/commit/2f9a18b48520c698014dbcfdc4776e74b6b4a219))

## [4.18.6](https://github.com/alex-feel/claude-code-toolbox/compare/v4.18.5...v4.18.6) (2026-01-19)


### Bug Fixes

* enable GitHub private repository access via API URL conversion ([f51fcdd](https://github.com/alex-feel/claude-code-toolbox/commit/f51fcddf5ac06b0a500973f6df934d6f7637ffc3))

## [4.18.5](https://github.com/alex-feel/claude-code-toolbox/compare/v4.18.4...v4.18.5) (2026-01-19)


### Bug Fixes

* enable multi-token authentication in bootstrap scripts ([4bce8b3](https://github.com/alex-feel/claude-code-toolbox/commit/4bce8b3a83cd45c37d74e1125ef94da571f4abae))

## [4.18.4](https://github.com/alex-feel/claude-code-toolbox/compare/v4.18.3...v4.18.4) (2026-01-13)


### Bug Fixes

* use PowerShell for Windows dependencies instead of bash ([9312145](https://github.com/alex-feel/claude-code-toolbox/commit/9312145a40c46315981ce44c002d6671658f4ca4))

## [4.18.3](https://github.com/alex-feel/claude-code-toolbox/compare/v4.18.2...v4.18.3) (2026-01-11)


### Bug Fixes

* prefer shell scripts over .cmd files for Git Bash MCP configuration ([5455f3f](https://github.com/alex-feel/claude-code-toolbox/commit/5455f3f6d2241b1c77a1e7e170b9c7616bc6f8e2))

## [4.18.2](https://github.com/alex-feel/claude-code-toolbox/compare/v4.18.1...v4.18.2) (2026-01-08)


### Bug Fixes

* unify MCP server STDIO execution to use bash and remove retry logic ([4c00bbc](https://github.com/alex-feel/claude-code-toolbox/commit/4c00bbc0d6830893d06e0c0336af0b0051a28e26))

## [4.18.1](https://github.com/alex-feel/claude-code-toolbox/compare/v4.18.0...v4.18.1) (2026-01-08)


### Bug Fixes

* resolve MCP server configuration retry missing PATH export ([64b3cde](https://github.com/alex-feel/claude-code-toolbox/commit/64b3cdef66c6357d4aa8a23360fd3d9e06b87bbc))

## [4.18.0](https://github.com/alex-feel/claude-code-toolbox/compare/v4.17.2...v4.18.0) (2026-01-07)


### Features

* add prompt hooks support to environment configuration ([48769e4](https://github.com/alex-feel/claude-code-toolbox/commit/48769e4c37c81196941fb77d503e399a481b9c53))

## [4.17.2](https://github.com/alex-feel/claude-code-toolbox/compare/v4.17.1...v4.17.2) (2026-01-07)


### Bug Fixes

* normalize extension case and prioritize Git Bash over WSL ([76974c6](https://github.com/alex-feel/claude-code-toolbox/commit/76974c628b72da8866d8464189e087cb7fdf2626))

## [4.17.1](https://github.com/alex-feel/claude-code-toolbox/compare/v4.17.0...v4.17.1) (2026-01-07)


### Bug Fixes

* convert Windows paths to Unix format for Git Bash execution ([e1d8856](https://github.com/alex-feel/claude-code-toolbox/commit/e1d88561e0f8ba75788a469f1f55c611225f29ee))

## [4.17.0](https://github.com/alex-feel/claude-code-toolbox/compare/v4.16.5...v4.17.0) (2026-01-07)


### Features

* use bash for CLI command execution on all platforms ([80949db](https://github.com/alex-feel/claude-code-toolbox/commit/80949db3160af866dd800d52816ca499ca212bd9))

## [4.16.5](https://github.com/alex-feel/claude-code-toolbox/compare/v4.16.4...v4.16.5) (2026-01-07)


### Bug Fixes

* use shell=True for Windows CMD URL escaping ([c02acab](https://github.com/alex-feel/claude-code-toolbox/commit/c02acab9411f2cc5ea11dd3d771c036ada4aed33))

## [4.16.4](https://github.com/alex-feel/claude-code-toolbox/compare/v4.16.3...v4.16.4) (2026-01-07)


### Bug Fixes

* escape HTTP MCP server URLs in Windows CMD execution ([dac75b1](https://github.com/alex-feel/claude-code-toolbox/commit/dac75b12d8521b75fe10f2f4f033a07b4cf13861))

## [4.16.3](https://github.com/alex-feel/claude-code-toolbox/compare/v4.16.2...v4.16.3) (2026-01-07)


### Bug Fixes

* quote HTTP MCP server URLs in shell commands ([4f475ca](https://github.com/alex-feel/claude-code-toolbox/commit/4f475ca4313007a72dddcf2bd3c4ff718fb3a188))

## [4.16.2](https://github.com/alex-feel/claude-code-toolbox/compare/v4.16.1...v4.16.2) (2026-01-06)


### Bug Fixes

* consolidate file validation into FileValidator class ([81fbf0e](https://github.com/alex-feel/claude-code-toolbox/commit/81fbf0e01837e9c3b8d1c5064d41fff011ac2a53))

## [4.16.1](https://github.com/alex-feel/claude-code-toolbox/compare/v4.16.0...v4.16.1) (2026-01-05)


### Bug Fixes

* display full URLs for skill files in validation output ([33ddfb0](https://github.com/alex-feel/claude-code-toolbox/commit/33ddfb048fa93e6413801a4a0defb3d2d1d932fb))
* handle binary file downloads in setup_environment.py ([bd348fe](https://github.com/alex-feel/claude-code-toolbox/commit/bd348fe7cd39d343017e11ccba1feb7b80839287))

## [4.16.0](https://github.com/alex-feel/claude-code-toolbox/compare/v4.15.0...v4.16.0) (2026-01-05)


### Features

* add config file support for status-line hooks ([d39dc61](https://github.com/alex-feel/claude-code-toolbox/commit/d39dc613ebfbf12b6e49e9b51dada50001c48ead))
* improve Node.js detection for MCP server configuration ([778f3a1](https://github.com/alex-feel/claude-code-toolbox/commit/778f3a17c86ad2907371d9c3e4755c83d917da59))


### Bug Fixes

* add files downloaded count to summary output ([a05bf75](https://github.com/alex-feel/claude-code-toolbox/commit/a05bf75472e4bb0fdfcc43b7a967ae011090e5f5))

## [4.15.0](https://github.com/alex-feel/claude-code-toolbox/compare/v4.14.0...v4.15.0) (2026-01-03)


### Features

* add version-conditional system prompt handling for v2.0.64+ ([78ce18d](https://github.com/alex-feel/claude-code-toolbox/commit/78ce18d7826e0731a9b7e27232daab8073ecfadc))

## [4.14.0](https://github.com/alex-feel/claude-code-toolbox/compare/v4.13.0...v4.14.0) (2026-01-02)


### Features

* add Fish shell support for environment variable management ([7e59976](https://github.com/alex-feel/claude-code-toolbox/commit/7e599766559be66715b9641ae19d4fa020f9bf89))

## [4.13.0](https://github.com/alex-feel/claude-code-toolbox/compare/v4.12.0...v4.13.0) (2026-01-02)


### Features

* add config file support for hooks ([04f596e](https://github.com/alex-feel/claude-code-toolbox/commit/04f596e8df2b8af380884f304647c6bd072c2770))

## [4.12.0](https://github.com/alex-feel/claude-code-toolbox/compare/v4.11.0...v4.12.0) (2026-01-01)


### Features

* add command-names array config with multi-name alias support ([bde67c3](https://github.com/alex-feel/claude-code-toolbox/commit/bde67c306c0a8578820fd7928c06237bf695cb9a))

## [4.11.0](https://github.com/alex-feel/claude-code-toolbox/compare/v4.10.1...v4.11.0) (2025-12-31)


### Features

* add attribution config support, deprecate includeCoAuthoredBy ([a3c6b53](https://github.com/alex-feel/claude-code-toolbox/commit/a3c6b53239b32ec48ee1211bed7ec48b5390ee61))
* add companyAnnouncements config support for custom announcements ([9469877](https://github.com/alex-feel/claude-code-toolbox/commit/94698773e57477ad33a0f28c9baef2cf2e8d149d))
* add status-line configuration support ([897b893](https://github.com/alex-feel/claude-code-toolbox/commit/897b893190295fbdc4a4a768ebaa23aca3075078))

## [4.10.1](https://github.com/alex-feel/claude-code-toolbox/compare/v4.10.0...v4.10.1) (2025-12-29)


### Bug Fixes

* pass version arg to bypass installer fresh install bug ([44f7f23](https://github.com/alex-feel/claude-code-toolbox/commit/44f7f23e6ecccbb375766e78d1fe8cb370c73afd))

## [4.10.0](https://github.com/alex-feel/claude-code-toolbox/compare/v4.9.0...v4.10.0) (2025-12-27)


### Features

* add on-demand Node.js LTS installation via install-nodejs config ([f6dd60e](https://github.com/alex-feel/claude-code-toolbox/commit/f6dd60ea1b162b1d0bc147d0e725c8c9f39db164))

## [4.9.0](https://github.com/alex-feel/claude-code-toolbox/compare/v4.8.1...v4.9.0) (2025-12-25)


### Features

* add refresh_path_from_registry() to fix Windows PATH propagation ([6dfe97c](https://github.com/alex-feel/claude-code-toolbox/commit/6dfe97c6f4ec190ee38a62a87987a54ee5bc6a26))


### Bug Fixes

* resolve Windows batch file commands in run_command() ([883ec81](https://github.com/alex-feel/claude-code-toolbox/commit/883ec81591b279ef153ca0763242dfa7ed2089ca))

## [4.8.1](https://github.com/alex-feel/claude-code-toolbox/compare/v4.8.0...v4.8.1) (2025-12-25)


### Bug Fixes

* install platform-specific dependencies before common ones ([90ea8b7](https://github.com/alex-feel/claude-code-toolbox/commit/90ea8b738d7e117099a2f6536c539f9a16ed6c35))

## [4.8.0](https://github.com/alex-feel/claude-code-toolbox/compare/v4.7.2...v4.8.0) (2025-12-25)


### Features

* add always-thinking-enabled config option ([bfe36cf](https://github.com/alex-feel/claude-code-toolbox/commit/bfe36cfcdd543a30536dcc7ec5a8dfa7cebd72d5))


### Bug Fixes

* add overwriting message for Skills file downloads ([c420284](https://github.com/alex-feel/claude-code-toolbox/commit/c420284f62336b580844a70a154e4a0fd1bf4618))
* correct settings message ([ff727e2](https://github.com/alex-feel/claude-code-toolbox/commit/ff727e21eaad73804ba182b1bd55552609d928c5))

## [4.7.2](https://github.com/alex-feel/claude-code-toolbox/compare/v4.7.1...v4.7.2) (2025-12-25)


### Bug Fixes

* improve console output formatting and separate hooks from settings ([f99a2a9](https://github.com/alex-feel/claude-code-toolbox/commit/f99a2a966dfd7e30516f52bb870c884c82347c44))

## [4.7.1](https://github.com/alex-feel/claude-code-toolbox/compare/v4.7.0...v4.7.1) (2025-12-25)


### Bug Fixes

* add consistent INFO messages for empty config sections ([bfb5426](https://github.com/alex-feel/claude-code-toolbox/commit/bfb542614154429f29ad1f3628c6d3da7a1917f9))

## [4.7.0](https://github.com/alex-feel/claude-code-toolbox/compare/v4.6.0...v4.7.0) (2025-12-24)


### Features

* add configuration inheritance support with top-level key override ([6847f7b](https://github.com/alex-feel/claude-code-toolbox/commit/6847f7b7f3745809110c751d2cc0eef285fd0673))
* add os-env-variables for cross-platform persistent environment variables ([c15e459](https://github.com/alex-feel/claude-code-toolbox/commit/c15e459e59f787d0fe8038dc51c80138228e9d3e))


### Bug Fixes

* correct duplicate step numbering in console output ([02887c1](https://github.com/alex-feel/claude-code-toolbox/commit/02887c16ab131a975fc4a7f3b0ea796f1ad44d38))
* use positive platform check to prevent MyPy unreachable error ([00c563e](https://github.com/alex-feel/claude-code-toolbox/commit/00c563eeff038bcf59946801f88f35d7ec176228))

## [4.6.0](https://github.com/alex-feel/claude-code-toolbox/compare/v4.5.1...v4.6.0) (2025-12-19)


### Features

* add support for multiple environment variables in MCP server configuration ([b721bac](https://github.com/alex-feel/claude-code-toolbox/commit/b721bac738ea774f2e66d69c8d79de8c41ff7570))

## [4.5.1](https://github.com/alex-feel/claude-code-toolbox/compare/v4.5.0...v4.5.1) (2025-12-03)


### Bug Fixes

* convert GitHub/GitLab tree URLs to raw URLs for skills validation ([edfe096](https://github.com/alex-feel/claude-code-toolbox/commit/edfe096c9fbd0d9466cee4f69430f7ec86175209))

## [4.5.0](https://github.com/alex-feel/claude-code-toolbox/compare/v4.4.0...v4.5.0) (2025-12-03)


### Features

* add skills installation support with base URL and files pattern ([8616e6f](https://github.com/alex-feel/claude-code-toolbox/commit/8616e6f9684614410968140caa3963d2d07f73e9))

## [4.4.0](https://github.com/alex-feel/claude-code-toolbox/compare/v4.3.0...v4.4.0) (2025-11-21)


### Features

* enable npm-to-native migration with specific versions ([4afef89](https://github.com/alex-feel/claude-code-toolbox/commit/4afef89241bca5846fd65f9787894d463dda0b51))

## [4.3.0](https://github.com/alex-feel/claude-code-toolbox/compare/v4.2.0...v4.3.0) (2025-11-21)


### Features

* add version parameter support and migration for native installers ([514beee](https://github.com/alex-feel/claude-code-toolbox/commit/514beeedb09d5dc91ffc64047eb7b81e416c4e68))

## [4.2.0](https://github.com/alex-feel/claude-code-toolbox/compare/v4.1.12...v4.2.0) (2025-11-20)


### Features

* add native Claude Code installation support ([44eefe7](https://github.com/alex-feel/claude-code-toolbox/commit/44eefe7b956e465811104068100e1db014a82f75))


### Bug Fixes

* remove unreachable return in install_claude_native_linux ([2606d67](https://github.com/alex-feel/claude-code-toolbox/commit/2606d67ce26e4e72b64a1ddc6998a1571503ab33))
* update native installation tests with proper mocks for CI ([a103933](https://github.com/alex-feel/claude-code-toolbox/commit/a10393311a7cc49ce8961e4f0fc10997b80c37c1))

## [4.1.12](https://github.com/alex-feel/claude-code-toolbox/compare/v4.1.11...v4.1.12) (2025-11-19)


### Bug Fixes

* use robust npm discovery to prevent WinError 193 on Windows ([6ef2ff6](https://github.com/alex-feel/claude-code-toolbox/commit/6ef2ff608376bfc9b46cca6aea1081ec327e6506))

## [4.1.11](https://github.com/alex-feel/claude-code-toolbox/compare/v4.1.10...v4.1.11) (2025-11-19)


### Bug Fixes

* prevent false positive when verifying Claude installation ([8f983b0](https://github.com/alex-feel/claude-code-toolbox/commit/8f983b0173ac874ddad51a785734deaf4c944119))

## [4.1.10](https://github.com/alex-feel/claude-code-toolbox/compare/v4.1.9...v4.1.10) (2025-11-19)


### Bug Fixes

* ensure claude command accessibility after native installer on Windows ([5641a73](https://github.com/alex-feel/claude-code-toolbox/commit/5641a73a5a34b21b75e00dd968c0f772a29e5974))

## [4.1.9](https://github.com/alex-feel/claude-code-toolbox/compare/v4.1.8...v4.1.9) (2025-11-18)


### Bug Fixes

* eliminate unnecessary PowerShell execution policy warnings ([9085bc4](https://github.com/alex-feel/claude-code-toolbox/commit/9085bc453041f6983d3df56fe0df206e472730ce))

## [4.1.8](https://github.com/alex-feel/claude-code-toolbox/compare/v4.1.7...v4.1.8) (2025-11-17)


### Bug Fixes

* add --no-project flag to prevent uv version conflicts ([0f7950a](https://github.com/alex-feel/claude-code-toolbox/commit/0f7950ad16e2950edc0c4a9ec09fa94817c76aa2))
* resolve argument length error in bootstrap scripts ([4ffa712](https://github.com/alex-feel/claude-code-toolbox/commit/4ffa712aa318559a4f04189a9ca0b0083682d797))

## [4.1.7](https://github.com/alex-feel/claude-code-toolbox/compare/v4.1.6...v4.1.7) (2025-11-17)


### Bug Fixes

* isolate hook execution from project Python requirements ([5e2516a](https://github.com/alex-feel/claude-code-toolbox/commit/5e2516aac62cbc556bfa4b5a05c4df547a25a764))

## [4.1.6](https://github.com/alex-feel/claude-code-toolbox/compare/v4.1.5...v4.1.6) (2025-11-16)


### Bug Fixes

* add version check for --append-system-prompt-file flag ([fe5cfc0](https://github.com/alex-feel/claude-code-toolbox/commit/fe5cfc06c2c4e22dd7c9ac732c415a15796e0a31))

## [4.1.5](https://github.com/alex-feel/claude-code-toolbox/compare/v4.1.4...v4.1.5) (2025-11-16)


### Bug Fixes

* use file-based flags to resolve argument list too long error ([664b6f8](https://github.com/alex-feel/claude-code-toolbox/commit/664b6f88ff3f7ab1f3246d433e8cd21bb1be9bac))

## [4.1.4](https://github.com/alex-feel/claude-code-toolbox/compare/v4.1.3...v4.1.4) (2025-11-15)


### Bug Fixes

* prevent Windows PATH pollution from temporary directories ([cb69080](https://github.com/alex-feel/claude-code-toolbox/commit/cb69080845a0866da82de831bbabaea38843823f))
* resolve MyPy unreachable code error in cleanup function ([a87a884](https://github.com/alex-feel/claude-code-toolbox/commit/a87a88409238b394e05e034e0ae3b2907f8ac445))

## [4.1.3](https://github.com/alex-feel/claude-code-toolbox/compare/v4.1.2...v4.1.3) (2025-11-15)


### Bug Fixes

* ensure uv-managed Python 3.12 is used regardless of system Python version ([9fbf4a5](https://github.com/alex-feel/claude-code-toolbox/commit/9fbf4a5c3558c79b65b766b05f6f8e0588671b65))
* expand tilde paths in dependency commands for proper execution ([5c0db4a](https://github.com/alex-feel/claude-code-toolbox/commit/5c0db4acba45631e3049a8489e912a96cd0a6c66))

## [4.1.2](https://github.com/alex-feel/claude-code-toolbox/compare/v4.1.1...v4.1.2) (2025-11-15)


### Bug Fixes

* detect Node.js v25 incompatibility and npm permission issues ([18684f2](https://github.com/alex-feel/claude-code-toolbox/commit/18684f2283c821078b715cc9dde8b6c2140152bc))
* improve PATH handling and system prompt summary messages ([54391e3](https://github.com/alex-feel/claude-code-toolbox/commit/54391e3c6fa4b9f50911f6d3c3657b6eeabf296b))

## [4.1.1](https://github.com/alex-feel/claude-code-toolbox/compare/v4.1.0...v4.1.1) (2025-11-15)


### Bug Fixes

* proper winreg typing for cross-platform type checking ([3397b84](https://github.com/alex-feel/claude-code-toolbox/commit/3397b84b4edd4dc12f1ffba1c3bf544ee9f616d1))
* resolve MyPy unreachable code error by inverting platform check ([6fde60e](https://github.com/alex-feel/claude-code-toolbox/commit/6fde60e6641713766de28371bfd124a8367dde0f))
* use Windows registry for reliable PATH registration ([532fe4d](https://github.com/alex-feel/claude-code-toolbox/commit/532fe4d6712722d306881426f54fe1a8a464dc46))

## [4.1.0](https://github.com/alex-feel/claude-code-toolbox/compare/v4.0.1...v4.1.0) (2025-11-14)


### Features

* add conditional system prompt loading for session continuity ([0e25808](https://github.com/alex-feel/claude-code-toolbox/commit/0e2580899fda146b0632b9d6ac362a138aa71617))


### Bug Fixes

* correct system prompt handling for session continuation ([8a5bb3b](https://github.com/alex-feel/claude-code-toolbox/commit/8a5bb3bb440ac5b69f2cea0c0ac4c8f40a40e7f7))

## [4.0.1](https://github.com/alex-feel/claude-code-toolbox/compare/v4.0.0...v4.0.1) (2025-11-14)


### Bug Fixes

* resolve system prompt application with command flags ([c67d4da](https://github.com/alex-feel/claude-code-toolbox/commit/c67d4da26738f59f6951c4cfa685729ac5247c34))

## [4.0.0](https://github.com/alex-feel/claude-code-toolbox/compare/v3.8.2...v4.0.0) (2025-11-14)


### ⚠ BREAKING CHANGES

* Output-style configuration is completely removed. Users must migrate to the new system-prompt mode field.

### Features

* remove output-style support and add system-prompt mode field ([43e100a](https://github.com/alex-feel/claude-code-toolbox/commit/43e100aad80bd3de333607dfe2491d674c13f86a))

## [3.8.2](https://github.com/alex-feel/claude-code-toolbox/compare/v3.8.1...v3.8.2) (2025-10-23)


### Bug Fixes

* resolve Git installer download failure on Windows ([811b50c](https://github.com/alex-feel/claude-code-toolbox/commit/811b50c2432983262b36bf78cd7de154ba79d577))

## [3.8.1](https://github.com/alex-feel/claude-code-toolbox/compare/v3.8.0...v3.8.1) (2025-10-19)


### Bug Fixes

* number steps correctly ([0c9195a](https://github.com/alex-feel/claude-code-toolbox/commit/0c9195a2f4931e1da9c8ae003e68f7613e6dae0a))

## [3.8.0](https://github.com/alex-feel/claude-code-toolbox/compare/v3.7.6...v3.8.0) (2025-10-19)


### Features

* implement file download/copy feature in environment setup ([f84c468](https://github.com/alex-feel/claude-code-toolbox/commit/f84c46890e1d6d40cca7fb609a4587d899d50ebf))

## [3.7.6](https://github.com/alex-feel/claude-code-toolbox/compare/v3.7.5...v3.7.6) (2025-10-16)


### Bug Fixes

* complete find_command to find_command_robust migration ([af160ec](https://github.com/alex-feel/claude-code-toolbox/commit/af160ecc06410b4a1cfded657f5c841448c953e6))
* complete find_command_robust migration in validation tests ([5ffa0be](https://github.com/alex-feel/claude-code-toolbox/commit/5ffa0bee00b8b8f1a8d224c61167dc1f22dc3980))
* resolve transient MCP server configuration failures ([5b9930f](https://github.com/alex-feel/claude-code-toolbox/commit/5b9930f18520609ed505c2e5c29fbf159677bff1))

## [3.7.5](https://github.com/alex-feel/claude-code-toolbox/compare/v3.7.4...v3.7.5) (2025-10-15)


### Bug Fixes

* correct argument order in claude mcp add for stdio servers ([f6fd6b8](https://github.com/alex-feel/claude-code-toolbox/commit/f6fd6b89f19c08e6e4f5dcca58a3fc333c11c373))
* replace PowerShell wrapper with direct subprocess for stdio MCP servers ([d7d8738](https://github.com/alex-feel/claude-code-toolbox/commit/d7d87380ff2df98936ab6a7b96d9ca862aeb8459))

## [3.7.4](https://github.com/alex-feel/claude-code-toolbox/compare/v3.7.3...v3.7.4) (2025-10-15)


### Bug Fixes

* prevent Node.js triple installation by updating PATH after winget ([fd2344c](https://github.com/alex-feel/claude-code-toolbox/commit/fd2344c850079ccb9e7a2f664ac6bac788f69f2c))

## [3.7.3](https://github.com/alex-feel/claude-code-toolbox/compare/v3.7.2...v3.7.3) (2025-10-14)


### Bug Fixes

* add missing quotes around command_str in PowerShell scripts ([a440c7b](https://github.com/alex-feel/claude-code-toolbox/commit/a440c7b5bf546f8d3b3a0993af07b3229d27beb4))
* add PATH propagation for stdio transport MCP servers on Windows ([d0ac563](https://github.com/alex-feel/claude-code-toolbox/commit/d0ac5635dd278832870c0f492136ed54d5d7e06a))
* add proper quoting for PowerShell script variables in stdio transport ([43f9681](https://github.com/alex-feel/claude-code-toolbox/commit/43f96814e782729d85e0f636085ef0b0a7b61548))
* complete base_cmd for Windows stdio retry mechanism ([c5802c0](https://github.com/alex-feel/claude-code-toolbox/commit/c5802c0cbe5308e908d117386c8ecbc2ba1969d2))
* correct argument order in MCP server configuration for stdio transport ([415efe8](https://github.com/alex-feel/claude-code-toolbox/commit/415efe8575012ebc29a3aa088a8551b0a6a3cd45))
* ensure Node.js PATH propagates to MCP configuration on Windows ([2c8f3be](https://github.com/alex-feel/claude-code-toolbox/commit/2c8f3be7820974cf9d916b097b75096441910325))

## [3.7.2](https://github.com/alex-feel/claude-code-toolbox/compare/v3.7.1...v3.7.2) (2025-10-13)


### Bug Fixes

* improve MSI installation comments and remove redundant parameter ([b1bef16](https://github.com/alex-feel/claude-code-toolbox/commit/b1bef164609d4cfca7aa765f8478d2e467a3e4eb))

## [3.7.1](https://github.com/alex-feel/claude-code-toolbox/compare/v3.7.0...v3.7.1) (2025-10-13)


### Bug Fixes

* resolve Windows installation encoding and MSI errors ([1d60fd5](https://github.com/alex-feel/claude-code-toolbox/commit/1d60fd559870c47bce0ec0356428cacab0b90e6c))

## [3.7.0](https://github.com/alex-feel/claude-code-toolbox/compare/v3.6.0...v3.7.0) (2025-10-06)


### Features

* use uv run for Python hook execution ([94cc17d](https://github.com/alex-feel/claude-code-toolbox/commit/94cc17db9bdfab6985b688914553330ef1e2d183))

## [3.6.0](https://github.com/alex-feel/claude-code-toolbox/compare/v3.5.1...v3.6.0) (2025-10-04)


### Features

* add automatic upgrade logic for claude-code-version latest ([c5e1df9](https://github.com/alex-feel/claude-code-toolbox/commit/c5e1df9afbd60c2a43c82d3099f575ca1e0e6f4a))

## [3.5.1](https://github.com/alex-feel/claude-code-toolbox/compare/v3.5.0...v3.5.1) (2025-10-03)


### Bug Fixes

* handle both bash and zsh shells on macOS for environment variables ([8bc5993](https://github.com/alex-feel/claude-code-toolbox/commit/8bc59930ff8d93fb840b9c6f216406acf32b6d97))

## [3.5.0](https://github.com/alex-feel/claude-code-toolbox/compare/v3.4.1...v3.5.0) (2025-10-02)


### Features

* add support for 'latest' value in claude-code-version config ([774482c](https://github.com/alex-feel/claude-code-toolbox/commit/774482c1ecbed19535cc13270cce8c0257c4e414))

## [3.4.1](https://github.com/alex-feel/claude-code-toolbox/compare/v3.4.0...v3.4.1) (2025-10-02)


### Bug Fixes

* make pause prompt conditional on UAC elevation type ([18bb371](https://github.com/alex-feel/claude-code-toolbox/commit/18bb3711b5cee95ebf1c96dde980b941aa107594))

## [3.4.0](https://github.com/alex-feel/claude-code-toolbox/compare/v3.3.1...v3.4.0) (2025-10-02)


### Features

* improve UAC elevation user experience ([cc93eb6](https://github.com/alex-feel/claude-code-toolbox/commit/cc93eb62b2d6ce6b16665fca479ff8f55fe77485))

## [3.3.1](https://github.com/alex-feel/claude-code-toolbox/compare/v3.3.0...v3.3.1) (2025-10-02)


### Bug Fixes

* improve UAC elevation environment variable passing ([87946f5](https://github.com/alex-feel/claude-code-toolbox/commit/87946f5e62a917f01aaa3b777b9102e6166e449b))

## [3.3.0](https://github.com/alex-feel/claude-code-toolbox/compare/v3.2.0...v3.3.0) (2025-10-02)


### Features

* implement automatic Windows UAC elevation ([3c26b17](https://github.com/alex-feel/claude-code-toolbox/commit/3c26b17dc984b6abf4dcbd4f1869df5484f40850))


### Bug Fixes

* resolve CI failures for Windows UAC elevation ([e984b8a](https://github.com/alex-feel/claude-code-toolbox/commit/e984b8a7ec46553f67faed8ef91bdd07efd05a33))

## [3.2.0](https://github.com/alex-feel/claude-code-toolbox/compare/v3.1.0...v3.2.0) (2025-10-01)


### Features

* add claude-code-version parameter to environment configs ([c73b56a](https://github.com/alex-feel/claude-code-toolbox/commit/c73b56aecfc8873a40a6df71dcbec9c099b49f13))

## [3.1.0](https://github.com/alex-feel/claude-code-toolbox/compare/v3.0.1...v3.1.0) (2025-10-01)


### Features

* add include-co-authored-by parameter to environment configs ([45416be](https://github.com/alex-feel/claude-code-toolbox/commit/45416bed0aa55d1179ad60a3aedd82b39d42d6f0))

## [3.0.1](https://github.com/alex-feel/claude-code-toolbox/compare/v3.0.0...v3.0.1) (2025-10-01)


### Bug Fixes

* resolve CI failures for type checking in GitHub Actions ([028f2a1](https://github.com/alex-feel/claude-code-toolbox/commit/028f2a1765bf3830fb30141f5acb146e6bf25743))

## [3.0.0](https://github.com/alex-feel/claude-code-toolbox/compare/v2.3.3...v3.0.0) (2025-10-01)


### ⚠ BREAKING CHANGES

* Dependencies structure changed from flat list to platform-specific dictionary. All existing environment configs must be updated.

### Features

* add platform-specific dependencies support ([6da97c6](https://github.com/alex-feel/claude-code-toolbox/commit/6da97c6c2c4f7e57dc54c120109cc69c5f859c56))

## [2.3.3](https://github.com/alex-feel/claude-code-toolbox/compare/v2.3.2...v2.3.3) (2025-10-01)


### Bug Fixes

* ensure Python 3.12 is used for hook execution on Unix systems ([ac9e0d2](https://github.com/alex-feel/claude-code-toolbox/commit/ac9e0d2cd7f282f709deb0aa5fd1097d5e38c7de))

## [2.3.2](https://github.com/alex-feel/claude-code-toolbox/compare/v2.3.1...v2.3.2) (2025-09-29)


### Bug Fixes

* remove MCP servers from all scopes to prevent conflicts ([38b5cfe](https://github.com/alex-feel/claude-code-toolbox/commit/38b5cfe3ea2299a4be822721028c3c198f64a5c9))

## [2.3.1](https://github.com/alex-feel/claude-code-toolbox/compare/v2.3.0...v2.3.1) (2025-09-26)


### Bug Fixes

* handle unbound variable error in setup scripts when piped to bash ([2561da2](https://github.com/alex-feel/claude-code-toolbox/commit/2561da2d48e5c481a9688676e212cec9144f0e06))

## [2.3.0](https://github.com/alex-feel/claude-code-toolbox/compare/v2.2.0...v2.3.0) (2025-09-25)


### Features

* force MCP server removal before re-adding to ensure config updates ([ef7a55b](https://github.com/alex-feel/claude-code-toolbox/commit/ef7a55bda9695e60bb1eb2c9c48f1ecda520775b))

## [2.2.0](https://github.com/alex-feel/claude-code-toolbox/compare/v2.1.0...v2.2.0) (2025-09-24)


### Features

* make command-name and command-defaults optional in environment configs ([e87f164](https://github.com/alex-feel/claude-code-toolbox/commit/e87f164ae5505f65f3d2cb1775745da0d130e41f))

## [2.1.0](https://github.com/alex-feel/claude-code-toolbox/compare/v2.0.0...v2.1.0) (2025-09-18)


### Features

* remove automatic MCP server permission addition feature ([28642e1](https://github.com/alex-feel/claude-code-toolbox/commit/28642e12ec52cd9efb96b9f4e1bdd875f4673061))

## [2.0.0](https://github.com/alex-feel/claude-code-toolbox/compare/v1.13.0...v2.0.0) (2025-09-14)


### ⚠ BREAKING CHANGES

* All pre-built library content has been removed from the repository. Users must now provide their own agents, hooks, slash commands, output styles, system prompts, and environment configurations. The toolbox now serves as a pure framework for Claude Code environment setup without any bundled content.

### Features

* remove all pre-built library content ([93ccd37](https://github.com/alex-feel/claude-code-toolbox/commit/93ccd37fbbc08b0c4986b1afaa83339021a66e2a))

## [1.13.0](https://github.com/alex-feel/claude-code-toolbox/compare/v1.12.0...v1.13.0) (2025-09-14)


### Features

* strengthen python-orchestrator workflow enforcement ([8feb171](https://github.com/alex-feel/claude-code-toolbox/commit/8feb17138f70eeb82f346c2a6146547ae5b9d232))


### Bug Fixes

* correct agent metadata and descriptions ([6fc87b7](https://github.com/alex-feel/claude-code-toolbox/commit/6fc87b7f9364e58b02a8d5acbcc5ebe1bf30cd3e))
* resolve output style names from front matter instead of filename ([b46e7da](https://github.com/alex-feel/claude-code-toolbox/commit/b46e7dabeb58e125dd2f9015ea562a4d8cf4652d))

## [1.12.0](https://github.com/alex-feel/claude-code-toolbox/compare/v1.11.2...v1.12.0) (2025-09-14)


### Features

* add python orchestrator output style and update configurations ([d676f5d](https://github.com/alex-feel/claude-code-toolbox/commit/d676f5d552168f159fe32fd2c670de6d038bdc88))


### Bug Fixes

* add missing front matter to python-developer agent ([afffdab](https://github.com/alex-feel/claude-code-toolbox/commit/afffdabf1b05522dae8c7c99bd8b3c450308227b))

## [1.11.2](https://github.com/alex-feel/claude-code-toolbox/compare/v1.11.1...v1.11.2) (2025-09-14)


### Bug Fixes

* make environment variable expansion tests platform-specific ([044daac](https://github.com/alex-feel/claude-code-toolbox/commit/044daac5aace8d625b5452b96cfd5b7c079f485f))
* resolve GitLab validation false positive in setup_environment.py ([8cb4a10](https://github.com/alex-feel/claude-code-toolbox/commit/8cb4a10857f85603e1229ebc19f10d162d79fd0f))

## [1.11.1](https://github.com/alex-feel/claude-code-toolbox/compare/v1.11.0...v1.11.1) (2025-09-14)


### Bug Fixes

* remove unnecessary releases_created output ([b0dd557](https://github.com/alex-feel/claude-code-toolbox/commit/b0dd55799a81074875e107008fe715a6652f0135))

## [1.11.0](https://github.com/alex-feel/claude-code-toolbox/compare/v1.10.0...v1.11.0) (2025-09-14)


### Features

* add local file path support to environment configurations ([85d9892](https://github.com/alex-feel/claude-code-toolbox/commit/85d98927aaa9fb7f30dec4a58c29bfd1b314f98a))
* remove structured output requirements from agents and generalize web researcher ([09fb566](https://github.com/alex-feel/claude-code-toolbox/commit/09fb566efe3bd70d51127c41c84e55f35aed831c))

## [1.10.0](https://github.com/alex-feel/claude-code-toolbox/compare/v1.9.1...v1.10.0) (2025-09-08)


### Features

* add pre-download validation for environment configurations ([dccf398](https://github.com/alex-feel/claude-code-toolbox/commit/dccf39827f295941254ae9c2757524c326920d72))
* add python-developer agent with comprehensive development protocol ([11ed6ce](https://github.com/alex-feel/claude-code-toolbox/commit/11ed6cebbe01919cdf752752f1d162794e36d674))


### Bug Fixes

* remove autoupdate functionality that causes hangs ([10da79a](https://github.com/alex-feel/claude-code-toolbox/commit/10da79ad0e20f9a4b62e85c300f920e24ba8bb75))
* remove unsupported option ([e2ff2ca](https://github.com/alex-feel/claude-code-toolbox/commit/e2ff2ca1daa2332fe8b91633ecbf114aac870f3e))

## [1.9.1](https://github.com/alex-feel/claude-code-toolbox/compare/v1.9.0...v1.9.1) (2025-09-06)


### Bug Fixes

* correct symlink test assertions for Unix platforms ([b068ff6](https://github.com/alex-feel/claude-code-toolbox/commit/b068ff6ed3a0dd470a6682f259b8015fba87d874))
* correct test assertions for register_global_command edge cases ([739fa00](https://github.com/alex-feel/claude-code-toolbox/commit/739fa000cf2aa545c469073ac140f9c5f6c1b787))
* move release-please skip condition to step level for matrix jobs ([7a1c019](https://github.com/alex-feel/claude-code-toolbox/commit/7a1c0194a9ba5eac5b3a9f0bf4c0cbe856165544))
* properly handle release-please PRs in matrix jobs ([6f5fd26](https://github.com/alex-feel/claude-code-toolbox/commit/6f5fd2691634a8c828996d7d54de88623acb19a9))
* resolve CI test failures and validation issues ([240b562](https://github.com/alex-feel/claude-code-toolbox/commit/240b562973c89d0f6ab13d3b672d35d5d7d2494e))
* skip Windows-specific tests on Unix platforms ([c871f5b](https://github.com/alex-feel/claude-code-toolbox/commit/c871f5bcec7abb8194e421755eae4e9c1f17d592))
* test workflow and dependency configuration ([fbe14fe](https://github.com/alex-feel/claude-code-toolbox/commit/fbe14fe6d90b8278d85131a513fb78f757e292f6))
* use uv run for install script tests ([b8d7d7d](https://github.com/alex-feel/claude-code-toolbox/commit/b8d7d7db92b258b416a5ead578dd27abb7d7dc03))

## [1.9.0](https://github.com/alex-feel/claude-code-toolbox/compare/v1.8.1...v1.9.0) (2025-09-05)


### Features

* add entity counting and badge generation system ([0c02bd8](https://github.com/alex-feel/claude-code-toolbox/commit/0c02bd8bce12390c84f6b0c3201fac2f830f06e4))
* add environment configuration validation system ([744fa75](https://github.com/alex-feel/claude-code-toolbox/commit/744fa75906c68013ece915639a15bce73a4f96c0))


### Bug Fixes

* add PR write permissions to validation workflow ([31458c0](https://github.com/alex-feel/claude-code-toolbox/commit/31458c01b017e57c1c6b5fca11178cc50afa8e5e))
* ensure validation workflow always runs to satisfy branch protection ([c0fd20c](https://github.com/alex-feel/claude-code-toolbox/commit/c0fd20c75ec9d6dda34fba5d3e4f18b43532d5df))
* remove --fix flag for better flow ([603cf05](https://github.com/alex-feel/claude-code-toolbox/commit/603cf053f7c923f7c864dc3df8ea9f05408c0568))
* remove gist creation from badge update workflow ([2ebbdc8](https://github.com/alex-feel/claude-code-toolbox/commit/2ebbdc8523d0151de3a9c8aae5d929c9de216352))
* skip validation workflow on Release Please PRs ([f22a961](https://github.com/alex-feel/claude-code-toolbox/commit/f22a96123e74876c9bc1e30f3b480376b967cfea))

## [1.8.1](https://github.com/alex-feel/claude-code-toolbox/compare/v1.8.0...v1.8.1) (2025-09-05)


### Bug Fixes

* add pause prompts to prevent terminal from auto-closing ([06b583d](https://github.com/alex-feel/claude-code-toolbox/commit/06b583da5752cd3320e7ae8adbb8577a60e74c41))
* convert GitLab web URLs to API format for authentication ([225b288](https://github.com/alex-feel/claude-code-toolbox/commit/225b288beadb13aa748b16df2c237cd9e954443a))
* pass authentication tokens to Python script for private repository support ([3ecb8e3](https://github.com/alex-feel/claude-code-toolbox/commit/3ecb8e394d167b5ab630cec3c502aeb618050b65))
* prevent PowerShell terminal from closing when using iex ([32316e7](https://github.com/alex-feel/claude-code-toolbox/commit/32316e79b80f86b75cae76c4350eaf3a82385c84))
* revert add pause prompts to prevent terminal from auto-closing ([232e84e](https://github.com/alex-feel/claude-code-toolbox/commit/232e84edb0e14262ec34014219688b216ada87f2))
* revert prevent PowerShell terminal from closing when using iex ([2c7ca3d](https://github.com/alex-feel/claude-code-toolbox/commit/2c7ca3d449fb748b371f9f8e4b208db6a4c8a576))
* strip query parameters from GitLab URLs to prevent Windows filename errors ([adb2904](https://github.com/alex-feel/claude-code-toolbox/commit/adb2904143989955c8e36707fecfa4b566fcf0f8))
* strip query parameters from system prompt filename in launcher script ([bf14fff](https://github.com/alex-feel/claude-code-toolbox/commit/bf14fffff708bb153eb5ab676ae91cb53d83b41c))

## [1.8.0](https://github.com/alex-feel/claude-code-toolbox/compare/v1.7.0...v1.8.0) (2025-09-05)


### Features

* add automatic Claude Code upgrade functionality ([2685031](https://github.com/alex-feel/claude-code-toolbox/commit/268503179e527c9e4cf4f0c5f8cd9357bd096366))
* add specialized research agents for code and web investigation ([2467cbf](https://github.com/alex-feel/claude-code-toolbox/commit/2467cbf110d244f6d6f4ff942f2efbfc06573570))
* support multiple environments with separate settings files ([d371647](https://github.com/alex-feel/claude-code-toolbox/commit/d371647e81db1c53f71f8ea5fd2c6bd2629ae4be))

## [1.7.0](https://github.com/alex-feel/claude-code-toolbox/compare/v1.6.0...v1.7.0) (2025-09-04)


### Features

* add flexible URL support for environment configurations ([179084a](https://github.com/alex-feel/claude-code-toolbox/commit/179084a5ed8c5d101df8bd1ca1e0ae6b7877d973))


### Bug Fixes

* auto-append {path} to base-url if not present ([d4ebbc7](https://github.com/alex-feel/claude-code-toolbox/commit/d4ebbc7964672e8ffc20bcbfabfb9fd6c6395f22))

## [1.6.0](https://github.com/alex-feel/claude-code-toolbox/compare/v1.5.0...v1.6.0) (2025-09-04)


### Features

* add environment variables configuration support ([4c15852](https://github.com/alex-feel/claude-code-toolbox/commit/4c15852ef05074e7cfdace2f60a22bf8718ea882))
* add model configuration and advanced permissions support ([a650047](https://github.com/alex-feel/claude-code-toolbox/commit/a650047f3469641ddaa8d82ac6d0413e985dbdd7))
* add private repository authentication support ([f8a157c](https://github.com/alex-feel/claude-code-toolbox/commit/f8a157cf41b3037f4a9f6a8d1c8193614dc5ec31))
* auto-configure MCP server permissions in additional-settings.json ([78d0a73](https://github.com/alex-feel/claude-code-toolbox/commit/78d0a73800c9ecb1090a42635d986e4cba9ee1b2))
* refactor environment config to support optional system prompts and output styles ([edd7469](https://github.com/alex-feel/claude-code-toolbox/commit/edd74699b19a384cf8a0dcf75997cd86d86a6acf))
* refactor hooks configuration to use separate files and events sections ([691304a](https://github.com/alex-feel/claude-code-toolbox/commit/691304af4eee820435c208ad694f9d9acb2a615c))
* support loading env configs from URLs, local files, or repository ([b8981c7](https://github.com/alex-feel/claude-code-toolbox/commit/b8981c748ac49b35fc1dd80ced06bbf73a486a49))
* use additional-settings.json for environment-specific hooks ([8d1a746](https://github.com/alex-feel/claude-code-toolbox/commit/8d1a7467c9c13d3028f3ed89415464ea93937dce))


### Bug Fixes

* make hooks cross-platform compatible ([fdc9540](https://github.com/alex-feel/claude-code-toolbox/commit/fdc9540d85e30594345dee7efcf23b4de0595281))
* resolve hook execution in Windows shells ([54d4f44](https://github.com/alex-feel/claude-code-toolbox/commit/54d4f4448d76bc90b3331d78c5e37464e04cb2fb))
* use forward slashes in hook paths to avoid JSON escaping issues ([7b0ed27](https://github.com/alex-feel/claude-code-toolbox/commit/7b0ed2778e817c15975f4df8df6bcebeb05f6629))

## [1.5.0](https://github.com/alex-feel/claude-code-toolbox/compare/v1.4.2...v1.5.0) (2025-09-03)


### Features

* transform setup system to be configuration-driven via YAML ([8751e1c](https://github.com/alex-feel/claude-code-toolbox/commit/8751e1c44ef7592bb2cc2a6b72d43fc4bbdd4651))


### Bug Fixes

* correct PowerShell command syntax and improve error handling ([274c642](https://github.com/alex-feel/claude-code-toolbox/commit/274c6426a2f7a8bfd22cc840a2c7da6f8e4a3a3e))
* resolve setup-environment.py runtime errors and improve reliability ([108fda5](https://github.com/alex-feel/claude-code-toolbox/commit/108fda54e69d7cdac8e93eb70601391f310cabdc))
* use uv's inline script dependencies for PyYAML ([abddc3e](https://github.com/alex-feel/claude-code-toolbox/commit/abddc3ef1a4343038656620bfef2b45a0287c6dd))

## [1.4.2](https://github.com/alex-feel/claude-code-toolbox/compare/v1.4.1...v1.4.2) (2025-08-16)


### Bug Fixes

* implement working PowerShell/CMD wrappers for claude-python command ([9a74e53](https://github.com/alex-feel/claude-code-toolbox/commit/9a74e5314c162655327d2e20cf7e1c0e0f0ecc12))
* properly escape PowerShell arguments with spaces in claude-python wrapper ([2b66ba5](https://github.com/alex-feel/claude-code-toolbox/commit/2b66ba51fee2ac8c4395d4e77550d4a9b4aee8a0))

## [1.4.1](https://github.com/alex-feel/claude-code-toolbox/compare/v1.4.0...v1.4.1) (2025-08-16)


### Bug Fixes

* bash wrapper now executes directly instead of going through PowerShell ([ce7a6d3](https://github.com/alex-feel/claude-code-toolbox/commit/ce7a6d3df8a66cb0865de40077d42406845a2f76))
* escape backslash in PowerShell regex pattern ([6508fd5](https://github.com/alex-feel/claude-code-toolbox/commit/6508fd51bc85bdebcfc677fbbc51a90ac49b76ac))
* use Git Bash to pass system prompt content on Windows ([d7105c2](https://github.com/alex-feel/claude-code-toolbox/commit/d7105c22fd74f6f5527fe1c824df59cb288e7c68))
* use Unix-style paths for system prompt loading on Windows ([7408a05](https://github.com/alex-feel/claude-code-toolbox/commit/7408a05924a537f6623c23d9c1c466a7e1b43a6f))

## [1.4.0](https://github.com/alex-feel/claude-code-toolbox/compare/v1.3.0...v1.4.0) (2025-08-16)


### Features

* add Git Bash support for claude-python command on Windows ([4720a8f](https://github.com/alex-feel/claude-code-toolbox/commit/4720a8f1285da7f43da055dfea11110df4f41681))

## [1.3.0](https://github.com/alex-feel/claude-code-toolbox/compare/v1.2.0...v1.3.0) (2025-08-16)


### Features

* incorporate YAGNI, DRY, KISS, and SOLID principles into Python developer prompt ([19b75ef](https://github.com/alex-feel/claude-code-toolbox/commit/19b75efad0f450ee130da3ba5f34439d70706d87))


### Bug Fixes

* add --scope user flag to MCP configuration commands ([d937ceb](https://github.com/alex-feel/claude-code-toolbox/commit/d937ceb251ec25ba2eedace41fbace16901eec10))
* add Node.js to PATH after MSI installation on Windows ([3f59280](https://github.com/alex-feel/claude-code-toolbox/commit/3f592809b73428f898ded33195d961bdeae90c71))
* correct Python version specifier syntax for uv ([df89b94](https://github.com/alex-feel/claude-code-toolbox/commit/df89b9482a042a95bf1c62dff378eba907ad47ee))
* correct uv PATH configuration in Windows PowerShell scripts ([4d1aa7e](https://github.com/alex-feel/claude-code-toolbox/commit/4d1aa7e0d107a36c3a9416a96f0c3fece717ed95))
* properly execute MCP configuration with full claude path ([c18f608](https://github.com/alex-feel/claude-code-toolbox/commit/c18f6083a461251893b51f159e8aa974cd4b3c58))
* properly handle SSL errors and npm path resolution ([d47ccee](https://github.com/alex-feel/claude-code-toolbox/commit/d47cceeb5c98856a9908bd88f88c841fe912cdd5))
* properly pass command-line arguments in PowerShell launcher ([587273d](https://github.com/alex-feel/claude-code-toolbox/commit/587273df2aba7989c8363f39e68dec01c6a8a9a4))
* resolve npm install failures and SSL certificate errors ([d3c80b4](https://github.com/alex-feel/claude-code-toolbox/commit/d3c80b4d8f39feeb2756578c78678ba58cebfaab))
* run MCP configuration in separate shell context ([e97f0dd](https://github.com/alex-feel/claude-code-toolbox/commit/e97f0ddb4f0acf5c027f4bcedbb6b66b5431198a))

## [1.2.0](https://github.com/alex-feel/claude-code-toolbox/compare/v1.1.4...v1.2.0) (2025-08-15)


### Features

* add cross-platform Python installer scripts ([f9a7ec3](https://github.com/alex-feel/claude-code-toolbox/commit/f9a7ec39d1ebaac1b5b576628afb68d1722fcac5))


### Bug Fixes

* configure MCP server without requiring npm in PATH ([30b40b6](https://github.com/alex-feel/claude-code-toolbox/commit/30b40b6e038e5bc7cd74bf1f7e9e054c1fb58c5a))
* resolve shebang and executable file issues ([51a92a1](https://github.com/alex-feel/claude-code-toolbox/commit/51a92a16eb996879d3da812de670bf2b6d2c5928))
* use correct setup-node action version v4 ([5d2bd5c](https://github.com/alex-feel/claude-code-toolbox/commit/5d2bd5cca6c13c0b97edff8602e2c92bb75e22c0))

## [1.1.4](https://github.com/alex-feel/claude-code-toolbox/compare/v1.1.3...v1.1.4) (2025-08-15)


### Bug Fixes

* use full path to claude command for MCP server configuration ([ae1552f](https://github.com/alex-feel/claude-code-toolbox/commit/ae1552f551aee5b113adff6e60f57386e280d1e9))

## [1.1.3](https://github.com/alex-feel/claude-code-toolbox/compare/v1.1.2...v1.1.3) (2025-08-15)


### Bug Fixes

* allow full Bash access in commit slash command ([8a85bc7](https://github.com/alex-feel/claude-code-toolbox/commit/8a85bc7380c37cbb586589abb7ac52ea77340d00))
* prevent Release Please PRs from blocking due to skipped required checks ([b7e37f4](https://github.com/alex-feel/claude-code-toolbox/commit/b7e37f4efb4ed9bc42497e7e7b1dc485d6b93b77))
* use proper claude mcp add command for Context7 server ([ddc0f04](https://github.com/alex-feel/claude-code-toolbox/commit/ddc0f0421c08ca4b58cc6dea7f71a02075b4fc1e))

## [1.1.2](https://github.com/alex-feel/claude-code-toolbox/compare/v1.1.1...v1.1.2) (2025-08-15)


### Bug Fixes

* prevent early exit in setup-python-environment.ps1 ([c9cd621](https://github.com/alex-feel/claude-code-toolbox/commit/c9cd621129dc8ebfc4d3805cb1c4209d93896786))

## [1.1.1](https://github.com/alex-feel/claude-code-toolbox/compare/v1.1.0...v1.1.1) (2025-08-15)


### Bug Fixes

* make setup-python-environment.ps1 compatible with iex execution ([f8bae80](https://github.com/alex-feel/claude-code-toolbox/commit/f8bae80d14a521a083294221be1ca3addce59abf))

## [1.1.0](https://github.com/alex-feel/claude-code-toolbox/compare/v1.0.2...v1.1.0) (2025-08-15)


### Features

* add comprehensive system prompts framework for Claude Code ([f68dabd](https://github.com/alex-feel/claude-code-toolbox/commit/f68dabd1d06c2e3f8a8847c1256ba25dd44b32b6))
* add global claude-python command registration to setup scripts ([d9cd0dd](https://github.com/alex-feel/claude-code-toolbox/commit/d9cd0dd0b35a2ca656dc612c570dbdc8e6fab3b5))
* add implementation-guide agent for comprehensive library documentation ([85bc4af](https://github.com/alex-feel/claude-code-toolbox/commit/85bc4afb0da18627f23eebc6cb19148d447ed4b3))
* add output styles feature with templates and examples ([10a67b5](https://github.com/alex-feel/claude-code-toolbox/commit/10a67b5bfae5b6c81488aa2cbd9ac1dfbfc9b562))
* add Python environment setup scripts for all platforms ([045a396](https://github.com/alex-feel/claude-code-toolbox/commit/045a39690f2073c13896b2360d84d44fece7d28b))
* enhance agent template with tool bundling rules and invocation triggers ([e3bd2b8](https://github.com/alex-feel/claude-code-toolbox/commit/e3bd2b8fb3ba07970d768906d8e4cadce7261fcf))
* enhance slash commands with comprehensive workflows and frontmatter support ([3f27b2d](https://github.com/alex-feel/claude-code-toolbox/commit/3f27b2db6aae45e926de0e48bfc7828f5293a94c))


### Bug Fixes

* add missing Edit tool to agents that use Write ([a62b7b5](https://github.com/alex-feel/claude-code-toolbox/commit/a62b7b5a458641432eff68517f531e974f8a42cb))
* correct critical documentation errors about system prompt usage ([6d48041](https://github.com/alex-feel/claude-code-toolbox/commit/6d480415ce0a993443ad2cecc655c1b03e1d8d88))
* remove non-existent subagents from system prompts README ([2a8c6ed](https://github.com/alex-feel/claude-code-toolbox/commit/2a8c6eda6df25394a0a4da2248a1b14e7ec694a4))
* resolve PowerShell script parse errors in setup-python-environment.ps1 ([df3445f](https://github.com/alex-feel/claude-code-toolbox/commit/df3445f6f6a02f1a6f60a3d57063f681a277aa71))
* resolve PSScriptAnalyzer warnings in setup-python-environment.ps1 ([fd00b9e](https://github.com/alex-feel/claude-code-toolbox/commit/fd00b9e03478ec33c157bc7b4cec1dc1f749c5b7))

## [1.0.2](https://github.com/alex-feel/claude-code-toolbox/compare/v1.0.1...v1.0.2) (2025-08-14)


### Bug Fixes

* replace security contact placeholder with GitHub advisories link ([f8842e5](https://github.com/alex-feel/claude-code-toolbox/commit/f8842e5a2c03d1d78264c829da6c451871f4d0d9))

## [1.0.1](https://github.com/alex-feel/claude-code-toolbox/compare/v1.0.0...v1.0.1) (2025-08-13)


### Bug Fixes

* remove redundant empty INFO message from Windows installer ([fbb996e](https://github.com/alex-feel/claude-code-toolbox/commit/fbb996ed720edd8b759dd64a0597cb4ec9bed9c3))

## 1.0.0 (2025-08-13)


### Features

* add initial version ([5f6efdc](https://github.com/alex-feel/claude-code-toolbox/commit/5f6efdcec856581d56e846601852bed5008de0cc))
