# iOS Device Build Wiring

When an iOS project built with xcodegen fails to install on a physical device from
the command line (signing errors, provisioning errors, "No matching provisioning
profile"), the fix is almost always missing signing config — not a code problem.

## Required wiring (project.yml)

```yaml
targets:
  YourApp:
    settings:
      base:
        CODE_SIGN_STYLE: Automatic
        DEVELOPMENT_TEAM: <10-char-team-id>
```

Find your team ID: Xcode → Account → Team, or `~/.claude/memory/` if previously recorded.

Regenerate after editing: `xcodegen generate`

## Required xcodebuild flags for device builds

```bash
xcodebuild \
  -scheme YourScheme \
  -project YourApp.xcodeproj \
  -destination 'generic/platform=iOS' \   # not a specific device ID
  -derivedDataPath DerivedData \
  -allowProvisioningUpdates \             # lets Xcode handle provisioning automatically
  build
```

Key differences from simulator builds:
- `generic/platform=iOS` instead of `platform=iOS Simulator,name=...`
- `-allowProvisioningUpdates` is required — without it, signing fails silently

## Auto-detect connected device

```python
import json, subprocess
devices = json.loads(subprocess.check_output(['xcrun', 'xcdevice', 'list']))
match = next((d for d in devices
              if not d.get('simulator')
              and d.get('platform') == 'com.apple.platform.iphoneos'
              and d.get('available')), None)
print(match['identifier'] if match else '')
```

Use in Makefile:

```makefile
DEVICE_ID ?= $(shell python3 -c "import json, subprocess; \
  devices = json.loads(subprocess.check_output(['xcrun', 'xcdevice', 'list'])); \
  match = next((d for d in devices if not d.get('simulator') \
    and d.get('platform') == 'com.apple.platform.iphoneos' \
    and d.get('available')), None); \
  print(match['identifier'] if match else '')")
```

## Install + launch after build

```bash
APP=$(find DerivedData -name "YourApp.app" -path "*/Debug-iphoneos/*" | head -1)
xcrun devicectl device install app --device "$DEVICE_ID" "$APP"
xcrun devicectl device process launch --device "$DEVICE_ID" --terminate-existing com.your.bundle.id
```

## Reference implementation

See `~/repos/dream/Makefile` — `ios-phone-build` + `ios-phone-install` + `ios-phone-launch`
targets use this exact pattern.
