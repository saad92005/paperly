# Security policy

Please report vulnerabilities privately through **GitHub → Security → Report a vulnerability** on this repository
(do not open public issues for security problems). We aim to acknowledge reports within 72 hours.

In scope: authentication/JWT handling, cross-user data access, SSRF via imports, prompt injection that leaks data,
XSS through rendered answers, and secrets exposure. The threat model and controls are in `docs/08-SECURITY-PRIVACY.md`.
