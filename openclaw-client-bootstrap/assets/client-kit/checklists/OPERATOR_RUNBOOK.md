# Operator Runbook

## Daily

1. Check service health:
```bash
sudo systemctl status openclaw --no-pager
sudo journalctl -u openclaw -n 100 --no-pager
tailscale status
```
2. Check approval target sanity (no `${env:...}` placeholder):
```bash
jq '.approvals.exec.targets' /home/openclaw/.openclaw/openclaw.json
```
3. Review pending approval requests at the OpenClawth portal.
4. Triage top proposals and approve/reject with rationale in the portal.
5. Check Telegram for any missed notification links.

## Weekly

1. Rotate any temporary tokens and remove stale pairings.
2. Run security audit:
```bash
sudo -u openclaw env HOME=/home/openclaw PATH=/home/openclaw/.openclaw/bin:$PATH \
  openclaw security audit --deep
```
3. Patch OS packages:
```bash
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get -y upgrade
sudo reboot
```

## Incident Response

1. Stop agent service:
```bash
sudo systemctl stop openclaw
```
2. Revoke exposed tokens immediately (gateway token, SPAPS credentials).
3. Remove suspicious pairings and tighten allowlists.
4. Diff configuration against version-controlled template.
5. Restore from known-good snapshot if integrity is uncertain.

## Change Management

1. All config changes require pull-request style review.
2. Any expansion of tool access needs explicit risk note.
3. Keep write credentials outside claw host.
4. Log approval owner for every executed write action (tracked by SPAPS).
