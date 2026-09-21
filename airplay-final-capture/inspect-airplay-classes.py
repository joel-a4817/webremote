#!/usr/bin/env python3

import json
import sys
import threading

import frida


AGENT = r'''
'use strict';

function exportAddress(name) {
    return Module.getGlobalExportByName(
        name
    );
}

const objcGetClass =
    new NativeFunction(
        exportAddress(
            'objc_getClass'
        ),
        'pointer',
        ['pointer']
    );

const objectGetClass =
    new NativeFunction(
        exportAddress(
            'object_getClass'
        ),
        'pointer',
        ['pointer']
    );

const classGetSuperclass =
    new NativeFunction(
        exportAddress(
            'class_getSuperclass'
        ),
        'pointer',
        ['pointer']
    );

const classGetName =
    new NativeFunction(
        exportAddress(
            'class_getName'
        ),
        'pointer',
        ['pointer']
    );

const classCopyMethodList =
    new NativeFunction(
        exportAddress(
            'class_copyMethodList'
        ),
        'pointer',
        [
            'pointer',
            'pointer'
        ]
    );

const methodGetName =
    new NativeFunction(
        exportAddress(
            'method_getName'
        ),
        'pointer',
        ['pointer']
    );

const selGetName =
    new NativeFunction(
        exportAddress(
            'sel_getName'
        ),
        'pointer',
        ['pointer']
    );

const freeMemory =
    new NativeFunction(
        exportAddress('free'),
        'void',
        ['pointer']
    );


function className(klass) {
    if (klass.isNull()) {
        return null;
    }

    const pointer =
        classGetName(klass);

    return pointer.isNull()
        ? null
        : pointer.readUtf8String();
}


function methodsForClass(klass) {
    if (klass.isNull()) {
        return [];
    }

    const countPointer =
        Memory.alloc(4);

    countPointer.writeU32(0);

    const list =
        classCopyMethodList(
            klass,
            countPointer
        );

    const count =
        countPointer.readU32();

    const methods = [];

    if (!list.isNull()) {
        for (
            let index = 0;
            index < count;
            index++
        ) {
            const method =
                list.add(
                    index
                    * Process.pointerSize
                ).readPointer();

            const selector =
                methodGetName(method);

            const namePointer =
                selGetName(selector);

            if (!namePointer.isNull()) {
                methods.push(
                    namePointer
                        .readUtf8String()
                );
            }
        }

        freeMemory(list);
    }

    return methods.sort();
}


function inspectClass(name) {
    const namePointer =
        Memory.allocUtf8String(
            name
        );

    const klass =
        objcGetClass(
            namePointer
        );

    if (klass.isNull()) {
        return {
            name: name,
            available: false
        };
    }

    const metaclass =
        objectGetClass(
            klass
        );

    const hierarchy = [];

    let current = klass;

    while (!current.isNull()) {
        hierarchy.push({
            name:
                className(current),
            instanceMethods:
                methodsForClass(
                    current
                )
        });

        current =
            classGetSuperclass(
                current
            );
    }

    return {
        name: name,
        available: true,
        classMethods:
            methodsForClass(
                metaclass
            ),
        hierarchy: hierarchy
    };
}


const names = [
    'MRAVRoutingDiscoverySession',
    'MRAVOutputContext',
    'MRAVConcreteOutputDevice',
    'MRAVOutputDevice',
    'MRAVEndpoint'
];

const result = names.map(
    inspectClass
);

send({
    event: 'inspection',
    classes: result
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
            "MusicUIService is not running. "
            "Open Music's AirPlay picker once."
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

    complete = threading.Event()
    result = {}

    def on_message(message, data):
        if message.get("type") == "send":
            payload = (
                message.get("payload")
                or {}
            )

            if (
                payload.get("event")
                == "inspection"
            ):
                result.update(
                    payload
                )

                complete.set()

        else:
            print(
                json.dumps(
                    message,
                    indent=2,
                ),
                flush=True,
            )

            complete.set()

    script.on(
        "message",
        on_message,
    )

    script.load()

    complete.wait(10)

    script.unload()
    session.detach()

    if "classes" not in result:
        raise RuntimeError(
            "No class inspection result"
        )

    output = (
        "/home/joel/"
        "airplay-final-capture/"
        "airplay-class-inspection.json"
    )

    with open(
        output,
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            result,
            handle,
            indent=2,
        )

        handle.write("\n")

    keywords = (
        "device",
        "route",
        "output",
        "endpoint",
        "discover",
        "available",
        "pickable",
        "uid",
        "name",
    )

    for class_record in result[
        "classes"
    ]:
        print()
        print(
            "====",
            class_record["name"],
            "====",
        )

        if not class_record.get(
            "available"
        ):
            print("not available")
            continue

        print("Class methods:")

        for method in class_record.get(
            "classMethods",
            []
        ):
            if any(
                keyword in method.lower()
                for keyword in keywords
            ):
                print(
                    "  +",
                    method,
                )

        for level in class_record.get(
            "hierarchy",
            []
        ):
            print(
                "Instance methods from",
                level.get("name"),
                ":",
            )

            for method in level.get(
                "instanceMethods",
                []
            ):
                if any(
                    keyword in method.lower()
                    for keyword in keywords
                ):
                    print(
                        "  -",
                        method,
                    )

    print()
    print(
        "Full result:",
        output,
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
