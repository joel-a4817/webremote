#!/usr/bin/env bash
set -euo pipefail

# Permanent deployer for Joel's iPad Web Remote.
# Install as: ~/webremote/deploy-to-ipad.sh

PROJECT="${WEBREMOTE_PROJECT:-$HOME/webremote}"
IPAD="${IPAD_HOST:-mobile@iPad4817}"
REMOTE="${WEBREMOTE_REMOTE_DIR:-/var/mobile/webremote}"
PYTHON_IPAD="${WEBREMOTE_IPAD_PYTHON:-/var/jb/usr/bin/python3}"
START_AFTER=0
INSTALL_PACKAGE=1
BUILD_PACKAGE=0

usage() {
    cat <<USAGE
Usage: $(basename "$0") [options]

Options:
  --start             Start the server after deployment.
  --no-package        Do not install the MediaCtl .deb package.
  --build-package     Run 'make clean package' before selecting the .deb.
  --host USER@HOST    Override iPad SSH target (default: $IPAD).
  --project DIR       Override local project (default: $PROJECT).
  -h, --help          Show this help.
USAGE
}

while (($#)); do
    case "$1" in
        --start) START_AFTER=1 ;;
        --no-package) INSTALL_PACKAGE=0 ;;
        --build-package) BUILD_PACKAGE=1 ;;
        --host) shift; IPAD="${1:?missing --host value}" ;;
        --project) shift; PROJECT="${1:?missing --project value}" ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
    shift
done

PROJECT="$(cd "$PROJECT" && pwd)"
for required in server.py sonobus-settingsctl.py web/index.html; do
    [[ -f "$PROJECT/$required" ]] || {
        echo "Missing required project file: $PROJECT/$required" >&2
        exit 1
    }
done

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
STAGE="$TMP/webremote"
mkdir -p "$STAGE"

echo '1/7 Validating local webremote source'
python3 -m py_compile "$PROJECT/server.py" "$PROJECT/sonobus-settingsctl.py"
if command -v node >/dev/null 2>&1; then
    while IFS= read -r -d '' file; do node --check "$file" >/dev/null; done \
        < <(find "$PROJECT/web" -type f -name '*.js' -print0)
fi

echo '2/7 Building clean iPad runtime payload'
install -m 755 "$PROJECT/server.py" "$STAGE/server.py"
install -m 755 "$PROJECT/sonobus-settingsctl.py" "$STAGE/sonobus-settingsctl.py"
cp -a "$PROJECT/web" "$STAGE/web"

# Include future top-level Python modules created by splitting server.py.
while IFS= read -r -d '' module; do
    name="$(basename "$module")"
    case "$name" in server.py|sonobus-settingsctl.py) continue ;; esac
    install -m 644 "$module" "$STAGE/$name"
done < <(find "$PROJECT" -maxdepth 1 -type f -name '*.py' -print0)

# The matching original launcher expects this file on the iPad.
cat > "$STAGE/stop-webremote.sh" <<'STOPPER'
#!/bin/sh
set -eu
DIR=/var/mobile/webremote
PIDFILE="$DIR/server.pid"
if [ -s "$PIDFILE" ]; then
    pid="$(cat "$PIDFILE" 2>/dev/null || true)"
    case "$pid" in
        ''|*[!0-9]*) ;;
        *)
            kill "$pid" 2>/dev/null || true
            count=0
            while kill -0 "$pid" 2>/dev/null && [ "$count" -lt 30 ]; do
                sleep 0.1
                count=$((count + 1))
            done
            kill -9 "$pid" 2>/dev/null || true
            ;;
    esac
fi
rm -f "$PIDFILE"
STOPPER
chmod 755 "$STAGE/stop-webremote.sh"
rm -f "$STAGE/sonobus-settings-path.txt"

if ((BUILD_PACKAGE)); then
    echo '3/7 Building native MediaCtl package'
    (cd "$PROJECT" && make clean package)
else
    echo '3/7 Using existing native MediaCtl package'
fi

DEB=''
if ((INSTALL_PACKAGE)); then
    DEB="$(find "$PROJECT/packages" "$PROJECT" -maxdepth 2 -type f \
        -name 'com.joel.mediactl_*iphoneos-arm64.deb' -printf '%T@ %p\n' 2>/dev/null \
        | sort -nr | head -n1 | cut -d' ' -f2-)"
    [[ -n "$DEB" && -f "$DEB" ]] || {
        echo 'No MediaCtl arm64 .deb found. Use --no-package or build it first.' >&2
        exit 1
    }
    echo "    Package: $DEB"
fi

echo '4/7 Stopping currently deployed server'
# Deploy stopper first so the original launcher and this deployer use one lifecycle.
scp -q "$STAGE/stop-webremote.sh" "$IPAD:/var/mobile/stop-webremote.webremote.tmp"
ssh "$IPAD" "set -e; mkdir -p '$REMOTE'; mv /var/mobile/stop-webremote.webremote.tmp '$REMOTE/stop-webremote.sh'; chmod 755 '$REMOTE/stop-webremote.sh'; '$REMOTE/stop-webremote.sh'"

if ((INSTALL_PACKAGE)); then
    echo '5/7 Installing complete native MediaCtl package'
    remote_deb="/var/mobile/$(basename "$DEB")"
    scp -q "$DEB" "$IPAD:$remote_deb"
    # sudo needs an interactive terminal for Joel's configured iPad.
    ssh -t "$IPAD" "sudo dpkg -i '$remote_deb'"
else
    echo '5/7 Native package skipped'
fi

echo '6/7 Replacing complete iPad webremote runtime atomically'
tar -C "$STAGE" -czf "$TMP/webremote-runtime.tar.gz" .
cat "$TMP/webremote-runtime.tar.gz" | ssh "$IPAD" \
    "set -e; rm -rf '${REMOTE}.new'; mkdir -p '${REMOTE}.new'; gzip -dc | tar -xf - -C '${REMOTE}.new'; chmod 755 '${REMOTE}.new/server.py' '${REMOTE}.new/sonobus-settingsctl.py' '${REMOTE}.new/stop-webremote.sh'; '$PYTHON_IPAD' -m py_compile '${REMOTE}.new/server.py' '${REMOTE}.new/sonobus-settingsctl.py'; rm -rf '${REMOTE}.old'; [ ! -d '$REMOTE' ] || mv '$REMOTE' '${REMOTE}.old'; mv '${REMOTE}.new' '$REMOTE'"

echo '7/7 Verifying deployed runtime'
ssh "$IPAD" "set -e; test -x '$REMOTE/server.py'; test -x '$REMOTE/sonobus-settingsctl.py'; test -x '$REMOTE/stop-webremote.sh'; test -f '$REMOTE/web/index.html'; '$PYTHON_IPAD' -m py_compile '$REMOTE/server.py' '$REMOTE/sonobus-settingsctl.py'"

if ((START_AFTER)); then
    echo 'Starting iPad Web Remote...'
    ssh "$IPAD" "set -e; cd '$REMOTE'; : > server.log; nohup '$PYTHON_IPAD' '$REMOTE/server.py' >>server.log 2>&1 </dev/null & echo \$! > server.pid; sleep 3; kill -0 \"\$(cat server.pid)\" 2>/dev/null || { cat server.log >&2; exit 1; }"
fi

echo
printf 'Deployment complete.\nLocal source: %s\niPad runtime: %s:%s\n' "$PROJECT" "$IPAD" "$REMOTE"
if ((START_AFTER)); then
    echo 'Server started.'
else
    echo 'Server left stopped. Use S once to start it.'
fi
