#!/usr/bin/env python3

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path


HOME = Path.home()

WEBREMOTE = (
    HOME
    / "webremote"
)

PAYLOAD = (
    HOME
    / "airplay-final-capture"
    / "request.bplist"
)

EXPECTED_LENGTH = 815

EXPECTED_HASH = (
    "8c0d0521437b8406ffc5814fa66f580a"
    "68b391a761eff911e0030a0c4f29442f"
)


def fail(message):
    raise SystemExit(
        "ERROR: " + message
    )


def find_unique(
    filename,
    required_text,
):
    matches = []

    for path in WEBREMOTE.rglob(
        filename
    ):
        if (
            ".git"
            in path.parts
        ):
            continue

        try:
            text = path.read_text(
                encoding="utf-8"
            )
        except UnicodeDecodeError:
            continue

        if required_text in text:
            matches.append(path)

    if len(matches) != 1:
        fail(
            f"expected one {filename}, "
            f"found {len(matches)}: "
            + ", ".join(
                str(path)
                for path in matches
            )
        )

    return matches[0]


def validate_payload():
    if not PAYLOAD.exists():
        fail(
            f"payload not found: {PAYLOAD}"
        )

    data = PAYLOAD.read_bytes()

    if len(data) != EXPECTED_LENGTH:
        fail(
            "payload length is "
            f"{len(data)}, expected "
            f"{EXPECTED_LENGTH}"
        )

    digest = hashlib.sha256(
        data
    ).hexdigest()

    if digest != EXPECTED_HASH:
        fail(
            "payload SHA-256 is "
            f"{digest}, expected "
            f"{EXPECTED_HASH}"
        )

    if not data.startswith(
        b"bplist00"
    ):
        fail(
            "payload is not a binary plist"
        )

    return data


def write_payload_header(
    payload,
    destination,
):
    lines = [
        "#pragma once",
        "",
        "#include <stddef.h>",
        "",
        "static const unsigned char",
        "kRt4817ModificationPayload[] = {",
    ]

    for offset in range(
        0,
        len(payload),
        12,
    ):
        chunk = payload[
            offset:offset + 12
        ]

        lines.append(
            "    "
            + ", ".join(
                f"0x{byte:02x}"
                for byte in chunk
            )
            + ","
        )

    lines.extend([
        "};",
        "",
        "static const size_t",
        "kRt4817ModificationPayloadLength =",
        "    sizeof("
        "kRt4817ModificationPayload"
        ");",
        "",
    ])

    destination.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def patch_mediactl(
    path,
):
    text = path.read_text(
        encoding="utf-8"
    )

    if (
        "sendRt4817RouteRequest"
        in text
    ):
        print(
            "MediaCtl source is already patched"
        )

        return

    backup = path.with_name(
        path.name + ".v1.5"
    )

    if not backup.exists():
        shutil.copy2(
            path,
            backup,
        )

    import_marker = (
        "#import <dlfcn.h>\n"
    )

    imports = '''#import <dlfcn.h>
#import <xpc/xpc.h>
#import <spawn.h>
#import <string.h>
#import <sys/wait.h>
#import <unistd.h>

#import "rt4817_request.h"

extern char **environ;
'''

    if import_marker not in text:
        fail(
            "dlfcn import was not found"
        )

    text = text.replace(
        import_marker,
        imports,
        1,
    )

    usage_marker = (
        '        "  mediactl '
        'now-playing-json\\n"\n'
    )

    if usage_marker not in text:
        fail(
            "usage insertion point "
            "was not found"
        )

    text = text.replace(
        usage_marker,
        usage_marker
        + '        "  mediactl '
          'airplay-rt4817\\n"\n'
        + '        "  mediactl '
          'restart-music\\n"\n',
        1,
    )

    main_marker = (
        "\nint main("
        "int argc, char *argv[]"
        ") {"
    )

    if main_marker not in text:
        fail(
            "main function was not found"
        )

    implementation = r'''
static int sendRt4817RouteRequest(void) {
    const char serviceName[] =
        "com.apple.mediaremoted.xpc";

    const char contextUID[] =
        "577E1BCA-2D9B-41C2-"
        "A8F8-C515CE8072D4";

    const uint64_t messageID =
        216172782113783848ULL;

    NSString *customID =
        NSUUID.UUID.UUIDString
            .uppercaseString;

    dispatch_queue_t queue =
        dispatch_get_global_queue(
            QOS_CLASS_USER_INITIATED,
            0
        );

    xpc_connection_t connection =
        xpc_connection_create_mach_service(
            serviceName,
            queue,
            0
        );

    if (connection == NULL) {
        fprintf(
            stderr,
            "Could not connect to "
            "mediaremoted.\n"
        );

        return 1;
    }

    xpc_connection_set_event_handler(
        connection,
        ^(xpc_object_t event) {
        }
    );

    xpc_connection_resume(
        connection
    );

    xpc_object_t message =
        xpc_dictionary_create(
            NULL,
            NULL,
            0
        );

    if (message == NULL) {
        fprintf(
            stderr,
            "Could not create the "
            "AirPlay request.\n"
        );

        return 1;
    }

    xpc_dictionary_set_data(
        message,
        "MRXPC_CONTEXT_MODIFICATION_DATA_KEY",
        kRt4817ModificationPayload,
        kRt4817ModificationPayloadLength
    );

    xpc_dictionary_set_string(
        message,
        "MRXPC_ROUTING_CONTEXT_UID_KEY",
        contextUID
    );

    xpc_dictionary_set_uint64(
        message,
        "MRXPC_MESSAGE_ID_KEY",
        messageID
    );

    xpc_dictionary_set_string(
        message,
        "MRXPC_MESSAGE_CUSTOM_ID_KEY",
        customID.UTF8String
    );

    xpc_object_t reply =
        xpc_connection_send_message_with_reply_sync(
            connection,
            message
        );

    if (reply == NULL) {
        fprintf(
            stderr,
            "mediaremoted returned no reply.\n"
        );

        return 1;
    }

    if (
        xpc_get_type(reply)
        == XPC_TYPE_ERROR
    ) {
        char *description =
            xpc_copy_description(
                reply
            );

        fprintf(
            stderr,
            "mediaremoted rejected "
            "the request: %s\n",
            description != NULL
                ? description
                : "unknown XPC error"
        );

        if (
            description != NULL
        ) {
            free(description);
        }

        return 1;
    }

    char *description =
        xpc_copy_description(
            reply
        );

    printf(
        "AirPlay request sent "
        "to rt4817\n"
    );

    printf(
        "Context: %s\n",
        contextUID
    );

    printf(
        "Device UID: "
        "07b32858-19ad-447c-898c-"
        "13d7f0ea07fe\n"
    );

    printf(
        "Custom ID: %s\n",
        customID.UTF8String
    );

    if (
        description != NULL
    ) {
        printf(
            "Reply: %s\n",
            description
        );

        free(description);
    }

    return 0;
}


static int runExecutable(
    const char *executable,
    char *const arguments[]
) {
    pid_t processID = 0;

    int result =
        posix_spawn(
            &processID,
            executable,
            NULL,
            NULL,
            arguments,
            environ
        );

    if (result != 0) {
        fprintf(
            stderr,
            "Could not run %s: %s\n",
            executable,
            strerror(result)
        );

        return result;
    }

    int status = 0;

    if (
        waitpid(
            processID,
            &status,
            0
        ) < 0
    ) {
        perror("waitpid");
        return 1;
    }

    if (
        !WIFEXITED(status)
    ) {
        return 1;
    }

    return WEXITSTATUS(status);
}


static int restartMusicInstance(void) {
    char *killArguments[] = {
        "killall",
        "-9",
        "Music",
        "MusicUIService",
        NULL
    };

    int killResult =
        runExecutable(
            "/usr/bin/killall",
            killArguments
        );

    if (killResult != 0) {
        runExecutable(
            "/var/jb/usr/bin/killall",
            killArguments
        );
    }

    usleep(700000);

    char *openArguments[] = {
        "uiopen",
        "music://",
        NULL
    };

    int openResult =
        runExecutable(
            "/usr/bin/uiopen",
            openArguments
        );

    if (openResult != 0) {
        openResult =
            runExecutable(
                "/var/jb/usr/bin/uiopen",
                openArguments
            );
    }

    if (openResult != 0) {
        fprintf(
            stderr,
            "Music was killed but could "
            "not be reopened.\n"
        );

        return 1;
    }

    printf(
        "Music and MusicUIService "
        "restarted\n"
    );

    return 0;
}

'''

    text = text.replace(
        main_marker,
        "\n"
        + implementation
        + main_marker,
        1,
    )

    command_marker = (
        "        NSDictionary"
        "<NSString *, NSNumber *> "
        "*commands = @{\n"
    )

    if command_marker not in text:
        fail(
            "transport command insertion "
            "point was not found"
        )

    command_handlers = r'''        if (
            [argument
                isEqualToString:
                    @"airplay-rt4817"]
        ) {
            return sendRt4817RouteRequest();
        }

        if (
            [argument
                isEqualToString:
                    @"restart-music"]
        ) {
            return restartMusicInstance();
        }

'''

    text = text.replace(
        command_marker,
        command_handlers
        + command_marker,
        1,
    )

    path.write_text(
        text,
        encoding="utf-8",
    )

    print(
        f"Patched {path}"
    )


def patch_makefile(
    path,
):
    text = path.read_text(
        encoding="utf-8"
    )

    line = (
        "mediactl_LDFLAGS += -lxpc\n"
    )

    if line not in text:
        if not text.endswith("\n"):
            text += "\n"

        text += line

        path.write_text(
            text,
            encoding="utf-8",
        )

    print(
        f"Updated {path}"
    )


def run(
    arguments,
    directory,
):
    print(
        "+ "
        + " ".join(arguments)
    )

    subprocess.run(
        arguments,
        cwd=directory,
        check=True,
    )


def main():
    payload = validate_payload()

    source = find_unique(
        "mediactl.m",
        "static int "
        "sendMediaRemoteCommand",
    )

    directory = source.parent

    makefile = (
        directory
        / "Makefile"
    )

    if not makefile.exists():
        fail(
            f"Makefile not found: "
            f"{makefile}"
        )

    header = (
        directory
        / "rt4817_request.h"
    )

    write_payload_header(
        payload,
        header,
    )

    patch_mediactl(
        source,
    )

    patch_makefile(
        makefile,
    )

    run(
        [
            "make",
            "clean",
        ],
        directory,
    )

    run(
        [
            "make",
            "package",
            "FINALPACKAGE=1",
        ],
        directory,
    )

    packages = sorted(
        (
            path
            for path
            in directory.rglob("packages")
            if path.is_dir()
        ),
        key=lambda item:
            item.stat().st_mtime,
        reverse=True,
    )

    package_files = []

    for package_directory in packages:
        for candidate in (
            package_directory.rglob(
                "*.deb"
            )
        ):
            package_files.append(
                candidate
            )

    if not package_files:
        fail(
            "build completed but no "
            "Debian package was found"
        )

    package = max(
        package_files,
        key=lambda item:
            item.stat().st_mtime,
    )

    output = (
        HOME
        / "airplay-final-capture"
        / "mediactl-v2.deb"
    )

    shutil.copy2(
        package,
        output,
    )

    print()
    print(
        f"PASS: package created at {output}"
    )


if __name__ == "__main__":
    main()
