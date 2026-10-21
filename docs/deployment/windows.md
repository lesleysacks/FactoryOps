# Windows factory deployment

The operator guide, commands, and manual factory-PC checklist are in the README under **Factory PC deployment (Windows)**.

Decision record: [ADR-003](../decisions/ADR-003-windows-local-deployment.md).

Scripts live in `deploy/windows/`. They are for Windows PowerShell 5.1. They are not a substitute for the Django application and they do not change domain models.

This repository checkout has not been installed on a factory PC. Treat the first install as a supervised trial: health check, login, one LAN client, one backup, and one restore into a temporary folder.
