# Changelog

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
