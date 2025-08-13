# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |

## Reporting a Vulnerability

We take security seriously. If you discover a security vulnerability, please follow these steps:

1. **DO NOT** open a public issue
2. Send details to: [security contact email]
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

## Security Best Practices

### For Users

1. **Verify Script Sources**
   - Always use HTTPS URLs
   - Pin to specific commits for production use
   - Review scripts before execution

2. **Use Official Sources**
   ```powershell
   # Good - official repository
   https://raw.githubusercontent.com/alex-feel/claude-code-toolbox/main/...

   # Bad - unknown source
   http://random-site.com/install.ps1
   ```

3. **Check Script Integrity**
   - Compare SHA256 checksums when available
   - Review code changes between versions

### For Contributors

1. **Never Commit Secrets**
   - API keys
   - Passwords
   - Personal access tokens
   - Private certificates

2. **Validate Input**
   - Sanitize user input
   - Validate file paths
   - Check command arguments

3. **Use Secure Defaults**
   - HTTPS over HTTP
   - User-scope over system-scope when possible
   - Explicit permissions over wildcards

## Known Security Considerations

### Windows PowerShell Execution Policy

The installer requires bypassing execution policy. Users should:
- Review the script before running
- Use `-ExecutionPolicy Bypass` only for trusted scripts
- Reset policy after installation if needed

### Elevation and Admin Rights

The installer may request elevation for:
- System-wide Git installation
- System-wide Node.js installation

This is normal behavior but users should:
- Understand why elevation is needed
- Prefer user-scope installations when possible

### Network Security

When behind corporate proxies:
- Use authenticated proxy settings securely
- Don't hardcode credentials in scripts
- Use environment variables for proxy configuration

## Security Updates

Security patches will be released as soon as possible after discovery. Watch this repository for updates.

## Compliance

This project aims to follow security best practices including:
- OWASP guidelines where applicable
- Principle of least privilege
- Defense in depth
- Secure by default
