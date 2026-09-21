#!/usr/bin/env python3

import json
import signal
import sys
import threading
from pathlib import Path

import frida


OUTPUT = (
    Path(__file__).resolve().parent
    / "native-picker-calls.jsonl"
)

stop_event = threading.Event()


AGENT = r'''
'use strict';


function exported(name) {
    return Module.getGlobalExportByName(
        name
    );
}


const objcGetClassList =
    new NativeFunction(
        exported('objc_getClassList'),
        'int',
        [
            'pointer',
            'int'
        ]
    );


const objectGetClass =
    new NativeFunction(
        exported('object_getClass'),
        'pointer',
        ['pointer']
    );


const classGetName =
    new NativeFunction(
        exported('class_getName'),
        'pointer',
        ['pointer']
    );


const classCopyMethodList =
    new NativeFunction(
        exported('class_copyMethodList'),
        'pointer',
        [
            'pointer',
            'pointer'
        ]
    );


const methodGetName =
    new NativeFunction(
        exported('method_getName'),
        'pointer',
        ['pointer']
    );


const methodGetImplementation =
    new NativeFunction(
        exported('method_getImplementation'),
        'pointer',
        ['pointer']
    );


const selGetName =
    new NativeFunction(
        exported('sel_getName'),
        'pointer',
        ['pointer']
    );


const freeMemory =
    new NativeFunction(
        exported('free'),
        'void',
        ['pointer']
    );


function readClassName(klass) {
    if (klass.isNull()) {
        return null;
    }

    const pointer =
        classGetName(klass);

    if (pointer.isNull()) {
        return null;
    }

    return pointer.readUtf8String();
}


function readSelectorName(method) {
    const selector =
        methodGetName(method);

    if (selector.isNull()) {
        return null;
    }

    const pointer =
        selGetName(selector);

    if (pointer.isNull()) {
        return null;
    }

    return pointer.readUtf8String();
}


function captureStack(context) {
    try {
        return Thread.backtrace(
            context,
            Backtracer.ACCURATE
        ).map(address => ({
            address:
                address.toString(),

            symbol:
                DebugSymbol
                    .fromAddress(address)
                    .toString()
        }));

    } catch (error) {
        return [{
            error:
                String(error)
        }];
    }
}


function relevantClass(name) {
    const lower =
        name.toLowerCase();

    return (
        lower.includes('routepicker')
        || lower.includes('routingview')
        || lower.includes('airplay')
        || lower.includes(
            'outputdevicepicker'
        )
        || lower.includes(
            'routingcontroller'
        )
    );
}


function relevantSelector(name) {
    const lower =
        name.toLowerCase();

    return (
        lower.includes('tap')
        || lower.includes('press')
        || lower.includes('click')
        || lower.includes('present')
        || lower.includes('show')
        || lower.includes('open')
        || lower.includes('picker')
        || lower.includes('route')
        || lower.includes('routing')
        || lower.includes('discover')
        || lower.includes('destination')
        || lower.includes('output')
        || lower.includes('popover')
        || lower.includes('menu')
    );
}


const classCount =
    objcGetClassList(
        ptr(0),
        0
    );


if (classCount <= 0) {
    throw new Error(
        'No Objective-C classes available'
    );
}


const classBuffer =
    Memory.alloc(
        classCount
        * Process.pointerSize
    );


const actualCount =
    objcGetClassList(
        classBuffer,
        classCount
    );


const installed = [];
const seenImplementations =
    new Set();


function hookMethod(
    classNameValue,
    method,
    kind
) {
    const selectorName =
        readSelectorName(method);

    if (
        selectorName === null
        || !relevantSelector(
            selectorName
        )
    ) {
        return;
    }

    const implementation =
        methodGetImplementation(
            method
        );

    if (
        implementation.isNull()
    ) {
        return;
    }

    const key =
        implementation.toString()
        + ':'
        + selectorName;

    if (
        seenImplementations.has(key)
    ) {
        return;
    }

    seenImplementations.add(key);

    Interceptor.attach(
        implementation,
        {
            onEnter(args) {
                send({
                    event:
                        'method-call',

                    timestamp:
                        new Date()
                            .toISOString(),

                    className:
                        classNameValue,

                    methodKind:
                        kind,

                    selector:
                        selectorName,

                    receiver:
                        args[0].toString(),

                    stack:
                        captureStack(
                            this.context
                        )
                });
            }
        }
    );

    installed.push({
        className:
            classNameValue,
        methodKind:
            kind,
        selector:
            selectorName,
        implementation:
            implementation.toString()
    });
}


function inspectMethodContainer(
    classNameValue,
    container,
    kind
) {
    if (container.isNull()) {
        return;
    }

    const countPointer =
        Memory.alloc(4);

    countPointer.writeU32(0);

    const methods =
        classCopyMethodList(
            container,
            countPointer
        );

    const count =
        countPointer.readU32();

    if (methods.isNull()) {
        return;
    }

    for (
        let index = 0;
        index < count;
        index++
    ) {
        const method =
            methods.add(
                index
                * Process.pointerSize
            ).readPointer();

        if (!method.isNull()) {
            hookMethod(
                classNameValue,
                method,
                kind
            );
        }
    }

    freeMemory(methods);
}


const matchingClasses = [];


for (
    let index = 0;
    index < actualCount;
    index++
) {
    const klass =
        classBuffer.add(
            index
            * Process.pointerSize
        ).readPointer();

    if (klass.isNull()) {
        continue;
    }

    const name =
        readClassName(klass);

    if (
        name === null
        || !relevantClass(name)
    ) {
        continue;
    }

    matchingClasses.push(name);

    inspectMethodContainer(
        name,
        klass,
        '-'
    );

    inspectMethodContainer(
        name,
        objectGetClass(klass),
        '+'
    );
}


send({
    event:
        'ready',

    pid:
        Process.id,

    matchingClasses:
        matchingClasses.sort(),

    installedHooks:
        installed.sort(
            (first, second) => {
                const left =
                    first.className
                    + first.selector;

                const right =
                    second.className
                    + second.selector;

                return left.localeCompare(
                    right
                );
            }
        )
});
'''


def log(message):
    print(
        message,
        flush=True,
    )


def stop_handler(
    signum,
    frame,
):
    stop_event.set()


def main():
    signal.signal(
        signal.SIGINT,
        stop_handler,
    )

    signal.signal(
        signal.SIGTERM,
        stop_handler,
    )

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

    log(
        "Attaching to MusicUIService "
        f"PID {process.pid}..."
    )

    session = device.attach(
        process.pid
    )

    script = session.create_script(
        AGENT
    )

    ready = threading.Event()

    output = OUTPUT.open(
        "w",
        encoding="utf-8",
        buffering=1,
    )

    def on_message(
        message,
        data,
    ):
        if (
            message.get("type")
            == "send"
        ):
            record = (
                message.get("payload")
                or {}
            )

            output.write(
                json.dumps(
                    record,
                    separators=(",", ":"),
                )
                + "\n"
            )

            output.flush()

            event = record.get(
                "event"
            )

            if event == "ready":
                ready.set()

                classes = record.get(
                    "matchingClasses",
                    [],
                )

                hooks = record.get(
                    "installedHooks",
                    [],
                )

                log(
                    f"Matched classes: "
                    f"{len(classes)}"
                )

                for name in classes:
                    log(
                        "  " + name
                    )

                log(
                    f"Installed hooks: "
                    f"{len(hooks)}"
                )

            elif event == "method-call":
                log("")
                log(
                    record.get(
                        "methodKind",
                        "?"
                    )
                    + "["
                    + str(
                        record.get(
                            "className"
                        )
                    )
                    + " "
                    + str(
                        record.get(
                            "selector"
                        )
                    )
                    + "]"
                )

                for frame in (
                    record.get("stack")
                    or []
                )[:8]:
                    log(
                        "  "
                        + str(
                            frame.get(
                                "symbol"
                            )
                        )
                    )

        else:
            log(
                "SCRIPT ERROR:"
            )

            log(
                json.dumps(
                    message,
                    indent=2,
                )
            )

            stop_event.set()

    script.on(
        "message",
        on_message,
    )

    script.load()

    if not ready.wait(10):
        raise RuntimeError(
            "Hook did not become ready"
        )

    log("")
    log(
        "Capture armed."
    )

    log(
        "Tap ONLY Music's working "
        "AirPlay button once."
    )

    log(
        "When the native picker appears, "
        "press Ctrl+C here."
    )

    while not stop_event.wait(
        0.25
    ):
        pass

    try:
        script.unload()
    finally:
        session.detach()
        output.close()

    log(
        f"Saved: {OUTPUT}"
    )


if __name__ == "__main__":
    try:
        main()

    except Exception as error:
        log(
            "ERROR: "
            f"{type(error).__name__}: "
            f"{error}"
        )

        sys.exit(1)
