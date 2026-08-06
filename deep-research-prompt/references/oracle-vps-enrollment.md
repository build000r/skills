# Oracle VPS enrollment over a tailnet SSH forward

ChatGPT login happens inside the one canonical browser profile on
`skillbox-portfolio-devbox`. Browser pixels and operator input cross an
authenticated SSH local forward; cookies, storage, tokens, browser profile
files, CDP, and target identifiers never leave the VPS.

This is an explicit human gate. Preparing the forward does not prove login,
identity, Pro capability, Project access, or doctor readiness.

## Prerequisites

- Node `.1.7` has started the VPS Xvfb browser host on display `:99` and kept
  CDP loopback-only.
- `skillbox-portfolio-devbox` resolves through MagicDNS and the operator Mac can
  run `ssh skillbox-portfolio-devbox true` without a public-IP target.
- VPS has `x11vnc`, noVNC's `novnc_proxy`, `python3`, `node`, `ss`, and the
  skills checkout at `/srv/skillbox/repos/skills`.
- Operator Mac has the same skills checkout or another trusted copy of
  `oracle-enroll-forward.sh`.

Do not install or expose a public VNC listener. The helper enforces
`127.0.0.1` for VNC and noVNC; SSH is the only transport.

## First enrollment: one command on the operator Mac

```bash
cd /Users/b/repos/opensource/skills
deep-research-prompt/assets/scripts/oracle-enroll-forward.sh start
```

That one command performs four bounded actions:

1. SSHes to `skillbox-portfolio-devbox` over its MagicDNS name.
2. Starts loopback-only `x11vnc` and noVNC against Xvfb display `:99`.
3. Starts `oracle-subagent-auth.mjs login --enroll-current-account --json` on
   the VPS. The command owns the deliberate reveal and later re-hide.
4. Creates an SSH control master with local port `6080` forwarded to the VPS
   loopback noVNC port, then opens the local noVNC page.

If the browser does not open automatically, use the exact loopback URL printed
by the command. Complete ChatGPT login in the displayed remote Chrome window.
Do not open ChatGPT in the Mac's normal Chrome profile for this enrollment.

For a previously enrolled profile whose session expired, use:

```bash
deep-research-prompt/assets/scripts/oracle-enroll-forward.sh start --reauth
```

The reauthentication path omits `--enroll-current-account`, preserving the
immutable enrolled identity policy.

## Observe without claiming completion

```bash
deep-research-prompt/assets/scripts/oracle-enroll-forward.sh status
```

`login_running:true` means the explicit login command is still waiting. A
stopped login process is not success proof by itself; only the post-teardown
doctor is authoritative.

## Tear down immediately after the visible login

```bash
deep-research-prompt/assets/scripts/oracle-enroll-forward.sh teardown
```

Teardown closes the exact SSH control socket and asks the VPS helper to stop
the enrollment login process, noVNC, and VNC. If login is still waiting, its
termination path re-hides Chrome before the display helpers stop.

Do not use `tailscale serve reset`, broad process kills, copied Chrome data, or
manual CDP exposure as cleanup shortcuts.

## Human acceptance gate after teardown

From the operator Mac, run the doctor on the VPS by MagicDNS name:

```bash
ssh skillbox-portfolio-devbox \
  'cd /srv/skillbox/repos/skills && sbp oracle --doctor'
```

Acceptance requires all of these after the forward is gone:

- doctor exits `0` with `ready:true`;
- exact enrolled identity and Pro capability checks are true;
- Project access and composer checks are true when a Project is configured;
- exact receipt PID, target/socket, listener, and hidden-state checks are true;
- Mac SSH control socket and private state file are absent;
- VPS enrollment-forward state is absent;
- no VNC/noVNC listener remains.

Absence checks:

```bash
test ! -e "$HOME/.oracle/oracle-enrollment-forward/state"
test ! -e "$HOME/.oracle/oracle-enrollment-forward/ssh-control"
ssh skillbox-portfolio-devbox \
  'test ! -e "$HOME/.oracle/oracle-subagent/enrollment-forward/state"'
```

These artifacts contain only process/port coordination metadata even while
active. No command in this flow reads, copies, prints, or transports cookies,
storage, tokens, policy fingerprints, browser target data, or backend payloads.

## Failure handling

| Stable failure | Action |
| --- | --- |
| `xvfb_display_missing` | Finish node `.1.7`; verify its user service created display `:99`. |
| `missing_dependency` / `novnc_missing` | Install the named VPS display dependency through the host provisioning lane; do not download an ad hoc binary in this flow. |
| `listener_not_loopback` | Stop. Remove the broad listener before retrying. |
| `login_command_failed` | Run the secret-free VPS auth doctor; repair receipt/profile/host readiness before another reveal. |
| `ssh_forward_failed` | Verify Tailnet membership, MagicDNS, and SSH policy; never substitute a raw Tailnet or public IP. |
| `auth_doctor_blocked` | Keep the Bead blocked. Use the returned stable reason codes; never inspect cookie or token values. |

If enrollment has not been completed by the operator, record exactly
`awaiting-operator-login`; never close the enrollment Bead from forward setup
or local syntax proof alone.
