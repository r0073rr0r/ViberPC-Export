# Security Policy

## Supported versions

This project tracks the `main` branch. Security fixes are applied to `main` and
released from there.

| Version | Supported |
| ------- | --------- |
| `main`  | ✅        |

## Reporting a vulnerability

Please **do not** open a public issue for security problems.

Instead, report privately through one of:

- GitHub's [private vulnerability reporting](https://github.com/r0073rr0r/ViberPC-Export/security/advisories/new)
  (**Security → Report a vulnerability**), or
- email **velimir.majstorov@meridianbet.com**.

Include a description, steps to reproduce, and the impact. You can expect an
initial response within a few days. Once a fix is available it will be released
on `main` and you will be credited unless you prefer to stay anonymous.

## Scope and safe use

This tool is designed to access **only** a local database that belongs to the
person running it, on their own machine. It performs no network communication
and sends nothing anywhere. Please keep reports focused on the tool itself
(e.g. accidental data leakage, unsafe file handling), not on using it against
data you do not own — that is out of scope and against the project's terms.
