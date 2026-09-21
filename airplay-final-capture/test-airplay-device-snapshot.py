#!/usr/bin/env python3

import json
import sys
import threading

import frida


AGENT = r'''
'use strict';

function globalExport(name) {
    return Module.getGlobalExportByName(
        name
    );
}

const objcGetClass =
    new NativeFunction(
        globalExport(
            'objc_getClass'
        ),
        'pointer',
        ['pointer']
    );

const selRegisterName =
    new NativeFunction(
        globalExport(
            'sel_registerName'
        ),
        'pointer',
        ['pointer']
    );

const classGetInstanceMethod =
    new NativeFunction(
        globalExport(
            'class_getInstanceMethod'
        ),
        'pointer',
        [
            'pointer',
            'pointer'
        ]
    );

const methodGetImplementation =
    new NativeFunction(
        globalExport(
            'method_getImplementation'
        ),
        'pointer',
        ['pointer']
    );

const objcMsgSendPointer =
    new NativeFunction(
        globalExport(
            'objc_msgSend'
        ),
        'pointer',
        [
            'pointer',
            'pointer'
        ]
    );

const objcMsgSendPointerIndex =
    new NativeFunction(
        globalExport(
            'objc_msgSend'
        ),
        'pointer',
        [
            'pointer',
            'pointer',
            'ulong'
        ]
    );

const objcMsgSendULong =
    new NativeFunction(
        globalExport(
            'objc_msgSend'
        ),
        'ulong',
        [
            'pointer',
            'pointer'
        ]
    );

const objcMsgSendBool =
    new NativeFunction(
        globalExport(
            'objc_msgSend'
        ),
        'bool',
        [
            'pointer',
            'pointer'
        ]
    );


function selector(name) {
    return selRegisterName(
        Memory.allocUtf8String(
            name
        )
    );
}


const countSelector =
    selector('count');

const objectAtIndexSelector =
    selector('objectAtIndex:');

const nameSelector =
    selector('name');

const localizedNameSelector =
    selector('localizedName');

const uidSelector =
    selector('uid');

const isPickableSelector =
    selector('isPickable');

const isLocalSelector =
    selector('isLocalDevice');

const respondsSelector =
    selector('respondsToSelector:');

const utf8Selector =
    selector('UTF8String');


function responds(
    object,
    targetSelector
) {
    if (
        object.isNull()
    ) {
        return false;
    }

    return Boolean(
        new NativeFunction(
            globalExport(
                'objc_msgSend'
            ),
            'bool',
            [
                'pointer',
                'pointer',
                'pointer'
            ]
        )(
            object,
            respondsSelector,
            targetSelector
        )
    );
}


function stringValue(
    object
) {
    if (
        object.isNull()
    ) {
        return null;
    }

    const pointer =
        objcMsgSendPointer(
            object,
            utf8Selector
        );

    if (
        pointer.isNull()
    ) {
        return null;
    }

    return pointer.readUtf8String();
}


function objectString(
    object,
    targetSelector
) {
    if (
        !responds(
            object,
            targetSelector
        )
    ) {
        return null;
    }

    const value =
        objcMsgSendPointer(
            object,
            targetSelector
        );

    return stringValue(
        value
    );
}


function objectBool(
    object,
    targetSelector
) {
    if (
        !responds(
            object,
            targetSelector
        )
    ) {
        return null;
    }

    return Boolean(
        objcMsgSendBool(
            object,
            targetSelector
        )
    );
}


const className =
    Memory.allocUtf8String(
        'MRAVRoutingDiscoverySession'
    );

const discoveryClass =
    objcGetClass(
        className
    );

if (
    discoveryClass.isNull()
) {
    throw new Error(
        'MRAVRoutingDiscoverySession unavailable'
    );
}


const setterSelector =
    selector(
        'setOutputDevicesSnapshot:'
    );

const setterMethod =
    classGetInstanceMethod(
        discoveryClass,
        setterSelector
    );

if (
    setterMethod.isNull()
) {
    throw new Error(
        'setOutputDevicesSnapshot: unavailable'
    );
}


const implementation =
    methodGetImplementation(
        setterMethod
    );


Interceptor.attach(
    implementation,
    {
        onEnter(args) {
            const array =
                args[2];

            if (
                array.isNull()
            ) {
                return;
            }

            const count =
                Number(
                    objcMsgSendULong(
                        array,
                        countSelector
                    )
                );

            const devices = [];

            for (
                let index = 0;
                index < count;
                index++
            ) {
                const device =
                    objcMsgSendPointerIndex(
                        array,
                        objectAtIndexSelector,
                        index
                    );

                if (
                    device.isNull()
                ) {
                    continue;
                }

                const name =
                    objectString(
                        device,
                        localizedNameSelector
                    )
                    ||
                    objectString(
                        device,
                        nameSelector
                    )
                    ||
                    'Unknown device';

                const uid =
                    objectString(
                        device,
                        uidSelector
                    );

                if (
                    uid === null
                ) {
                    continue;
                }

                devices.push({
                    name: name,
                    uid: uid,
                    pickable:
                        objectBool(
                            device,
                            isPickableSelector
                        ),
                    local:
                        objectBool(
                            device,
                            isLocalSelector
                        )
                });
            }

            send({
                event:
                    'device-snapshot',
                count:
                    devices.length,
                devices:
                    devices
            });
        }
    }
);


send({
    event: 'ready'
});
'''


def main():
    device = (
        frida
        .get_device_manager()
        .add_remote_device(
            "127.0.0.1:27042"
        )
    )

    process = next(
        (
            item
            for item
            in device.enumerate_processes()
            if item.name
            == "MusicUIService"
        ),
        None,
    )

    if process is None:
        raise RuntimeError(
            "MusicUIService is not running"
        )

    print(
        "Attaching to MusicUIService "
        f"PID {process.pid}...",
        flush=True,
    )

    session = device.attach(
        process.pid
    )

    script = session.create_script(
        AGENT
    )

    ready = threading.Event()
    captured = threading.Event()
    result = {}

    def on_message(message, data):
        if message.get("type") != "send":
            print(
                json.dumps(
                    message,
                    indent=2,
                ),
                flush=True,
            )

            captured.set()
            return

        payload = (
            message.get("payload")
            or {}
        )

        event = payload.get(
            "event"
        )

        if event == "ready":
            ready.set()

        elif event == "device-snapshot":
            result.clear()
            result.update(
                payload
            )

            print()
            print(
                "Native AirPlay devices:"
            )

            for item in payload.get(
                "devices",
                [],
            ):
                print()
                print(
                    item.get("name")
                )

                print(
                    "  UID:",
                    item.get("uid")
                )

                print(
                    "  Pickable:",
                    item.get("pickable")
                )

                print(
                    "  Local:",
                    item.get("local")
                )

            captured.set()

    script.on(
        "message",
        on_message,
    )

    script.load()

    if not ready.wait(10):
        raise RuntimeError(
            "Agent did not become ready"
        )

    print()
    print(
        "Open Music's AirPlay picker now."
    )

    print(
        "Do not select anything."
    )

    if not captured.wait(30):
        raise RuntimeError(
            "No device snapshot was received"
        )

    script.unload()
    session.detach()

    if "devices" not in result:
        raise RuntimeError(
            "Snapshot capture failed"
        )

    output = (
        "/home/joel/"
        "airplay-final-capture/"
        "airplay-devices.json"
    )

    with open(
        output,
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            {
                "devices":
                    result["devices"]
            },
            handle,
            indent=2,
        )

        handle.write("\n")

    print()
    print(
        "Saved:",
        output
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(
            "ERROR:",
            type(error).__name__,
            str(error),
            file=sys.stderr,
        )

        sys.exit(1)
