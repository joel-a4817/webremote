#!/var/jb/usr/bin/python3
import argparse, json, os, plistlib, shutil, subprocess, sys, time
import xml.etree.ElementTree as ET
from pathlib import Path

SETTINGS_ROOT = Path("/var/mobile/Containers/Data/Application")
SETTINGS_SUFFIX = Path("Library/Application Support/SonoBus/SonoBus.settings")
PARAMS = {
    "send-muted": "mastsendmute",
    "receive-muted": "mastrecvmute",
    "input-muted": "mastinmute",
    "monitor-solo": "mastmonsolo",
}
FIXED = {
    "defsendqual": "5.0",
    "sendchannels": "2.0",
    "reconnectlast": "1.0",
}


def discover_settings():
    roots = (
        Path("/var/mobile/Containers/Data/Application"),
        Path("/private/var/mobile/Containers/Data/Application"),
    )
    locator = Path(__file__).resolve().with_name("sonobus-settings-path.txt")
    override = os.environ.get("SONOBUS_SETTINGS", "").strip()

    def valid(path):
        try:
            return path.is_file() and path.stat().st_size > 0
        except OSError:
            return False

    if override:
        candidate = Path(override).expanduser()
        if valid(candidate):
            return candidate.resolve()

    try:
        cached_text = locator.read_text(encoding="utf-8").strip()
        if cached_text:
            cached = Path(cached_text)
            if valid(cached):
                return cached.resolve()
    except OSError:
        pass

    candidates = []
    for root in roots:
        try:
            containers = list(root.iterdir())
        except OSError:
            continue
        for container in containers:
            metadata = container / ".com.apple.mobile_container_manager.metadata.plist"
            bundle_id = ""
            try:
                with metadata.open("rb") as handle:
                    payload = plistlib.load(handle)
                bundle_id = str(
                    payload.get("MCMMetadataIdentifier")
                    or payload.get("MCMMetadataInfo", {}).get("MCMMetadataIdentifier")
                    or ""
                )
            except (OSError, ValueError, plistlib.InvalidFileException, AttributeError):
                pass
            direct = container / SETTINGS_SUFFIX
            if bundle_id == "com.Sonosaurus.SonoBus" and valid(direct):
                candidates.append(direct)
                continue
            if valid(direct):
                candidates.append(direct)

    if not candidates:
        # Last-resort lookup through the already-proven historic settings path
        # is intentionally not embedded. The user can place any valid path in
        # sonobus-settings-path.txt without changing code.
        raise RuntimeError(
            "SonoBus preferences are not discoverable from this process. "
            "Open SonoBus once, then run the included locate-sonobus-settings.sh script."
        )

    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    selected = candidates[0].resolve()
    try:
        locator.write_text(str(selected) + "\n", encoding="utf-8")
        os.chmod(locator, 0o600)
    except OSError:
        pass
    return selected


def boolean(v):
    v=str(v).lower()
    if v in ('1','on','true','yes'): return '1.0'
    if v in ('0','off','false','no'): return '0.0'
    raise argparse.ArgumentTypeError(v)

def document():
    settings = discover_settings()
    tree=ET.parse(settings); root=tree.getroot()
    sono=root.find("./VALUE[@name='filterStateXML']/SonoBusAoO")
    if sono is None: raise RuntimeError('SonoBusAoO missing')
    return settings,tree,root,sono


def find_executable(name):
    discovered = shutil.which(name)
    if discovered:
        return discovered
    for directory in ("/var/jb/usr/bin", "/var/jb/usr/local/bin", "/usr/bin", "/bin"):
        candidate = Path(directory) / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None

def stop():
    executable = find_executable("killall")
    if executable is None:
        raise RuntimeError("killall was not found")
    subprocess.run(
        [executable, "SonoBus"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    time.sleep(1.5)


def launch():
    executable = find_executable("uiopen")
    if executable is None:
        raise RuntimeError("uiopen was not found")
    try:
        subprocess.Popen(
            [executable, "sonobus://"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as error:
        raise RuntimeError(f"Could not launch SonoBus: {error}") from error


def connection_element(sono, create=False):
    recent = sono.find('./RecentConnections')
    if recent is None and create:
        recent = ET.SubElement(sono, 'RecentConnections')
    if recent is None:
        return None
    connection = recent.find('./ServerConnectionInfo')
    if connection is None and create:
        connection = ET.SubElement(recent, 'ServerConnectionInfo')
    return connection


def apply(a):
    settings, tree, root, sono = document()
    params = {
        item.get('id'): item
        for item in sono.findall('./PARAM')
        if item.get('id')
    }
    missing = [key for key in (*FIXED, *PARAMS.values()) if key not in params]
    if missing:
        raise RuntimeError('Missing SonoBus parameters: ' + ', '.join(missing))

    connection = connection_element(sono, create=True)
    if a.username is not None:
        connection.set('userName', a.username)
    if a.group is not None:
        connection.set('groupName', a.group)
    if a.password is not None:
        connection.set('groupPassword', a.password)
    connection.set('serverHost', a.server)
    connection.set('serverPort', str(a.port))
    connection.set('groupIsPublic', '0')
    connection.set('userPassword', connection.get('userPassword', ''))
    connection.set('timestamp', str(int(time.time() * 1000)))

    for key, value in FIXED.items():
        params[key].set('value', value)
    for argument, identifier in PARAMS.items():
        value = getattr(a, argument.replace('-', '_'))
        if value is not None:
            params[identifier].set('value', value)

    if a.peer:
        peer = next((item for item in sono.findall('./PeerStateCacheMap/PeerStateCache') if item.get('name') == a.peer), None)
        if peer is not None:
            peer.set('sendformat', str(a.peer_format))

    override = next((item for item in root.findall('./VALUE') if item.get('name') == 'shouldOverrideSampleRate'), None)
    if override is None:
        override = ET.SubElement(root, 'VALUE', {'name': 'shouldOverrideSampleRate'})
    override.set('val', '1')

    tmp = settings.with_suffix(settings.suffix + '.tmp')
    bak = settings.with_suffix(settings.suffix + '.backup')
    shutil.copy2(settings, bak)
    ET.indent(tree, space='  ')
    tree.write(tmp, encoding='UTF-8', xml_declaration=True)
    os.chown(tmp, 501, 501)
    os.chmod(tmp, 0o644)
    os.replace(tmp, settings)
    if a.launch:
        launch()


def state():
    settings, _, _, sono = document()
    params = {
        item.get('id'): item.get('value')
        for item in sono.findall('./PARAM')
        if item.get('id')
    }
    connection = connection_element(sono, create=False)
    def attribute(name, default=''):
        return connection.get(name, default) if connection is not None else default
    print(json.dumps({
        'settingsPath': str(settings),
        'username': attribute('userName'),
        'group': attribute('groupName'),
        'passwordRequired': bool(attribute('groupPassword')),
        'sendMuted': params.get('mastsendmute') == '1.0',
        'receiveMuted': params.get('mastrecvmute') == '1.0',
        'inputMuted': params.get('mastinmute') == '1.0',
        'monitorSolo': params.get('mastmonsolo') == '1.0',
        'sendQualityIndex': params.get('defsendqual'),
        'sendChannels': params.get('sendchannels'),
        'reconnectLast': params.get('reconnectlast'),
    }, separators=(',', ':')))


def main():
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest='cmd',required=True); sub.add_parser('state'); a=sub.add_parser('apply')
    for x in ('username','group','password'): a.add_argument('--'+x)
    a.add_argument('--server',default='aoo.sonobus.net'); a.add_argument('--port',type=int,default=10998); a.add_argument('--peer',default='rt4817'); a.add_argument('--peer-format',default='5')
    for x in PARAMS: a.add_argument('--'+x,type=boolean)
    a.add_argument('--launch',action='store_true'); ns=p.parse_args(); state() if ns.cmd=='state' else apply(ns)
if __name__=='__main__':
    try: main()
    except Exception as e: print('ERROR:',e,file=sys.stderr); raise SystemExit(1)
