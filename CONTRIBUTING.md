# Contributing Guide

## Branches
- `main` is our master branch. It is protected: no direct pushes, no force pushes, no deletion.
- Create a branch for every change:
  - `feature/<short-description>` — new features
  - `fix/<short-description>` — bug fixes
  - `docs/<short-description>` — documentation
  - `chore/<short-description>` — setup and maintenance

## Workflow
1. Create or pick an issue on the project board and assign yourself.
2. Create a branch from the latest `main`.
3. Commit your work with clear messages.
4. Open a pull request into `main` and link the issue (`Closes #<number>`).
5. At least one teammate reviews and approves. All review comments must be resolved.
6. Merge the pull request and delete the branch.

## Commit Messages
Use the format `<type>: <summary>`, for example:
- `feat: add campus location list`
- `fix: reject empty chat messages`
- `docs: update setup instructions`

Types: `feat`, `fix`, `docs`, `chore`, `test`, `refactor`, `style`.

## Secrets
Never commit passwords, API keys, or `.env` files. Share secrets privately with teammates.
