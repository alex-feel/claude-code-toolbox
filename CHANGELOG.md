# Changelog

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
