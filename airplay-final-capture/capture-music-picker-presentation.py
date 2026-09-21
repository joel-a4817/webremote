#!/usr/bin/env python3

import json
import signal
import sys
import threading
from pathlib import Path

import frida


OUTPUT = (
    Path(__file__).resolve().parent
    / "music-picker-presentations.jsonl"
)

stop_event = threading.Event()


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


const objectGetClass =
    new NativeFunction(
        globalExport(
            'object_getClass'
        ),
        'pointer',
        ['pointer']
    );


const classGetName =
    new NativeFunction(
        globalExport(
            'class_getName'
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


function selector(name) {
    return selRegisterName(
        Memory.allocUtf8String(
            name
        )
    );
}


const titleSelector =
    selector('title');

const accessibilityIdentifierSelector =
    selector(
        'accessibilityIdentifier'
    );

const utf8StringSelector =
    selector('UTF8String');


function className(object) {
    if (
        object === null ||
        object === undefined ||
        object.isNull()
    ) {
        return null;
    }

    try {
        const klass =
            objectGetClass(object);

        if (klass.isNull()) {
            return null;
        }

        const pointer =
            classGetName(klass);

        return pointer.isNull()
            ? null
            : pointer.readUtf8String();

    } catch (error) {
        return null;
    }
}


function stringValue(value) {
    if (
        value === null ||
        value === undefined ||
        value.isNull()
    ) {
        return null;
    }

    try {
        const pointer =
            objcMsgSendPointer(
                value,
                utf8StringSelector
            );

        return pointer.isNull()
            ? null
            : pointer.readUtf8String();

    } catch (error) {
        return null;
    }
}


function stringProperty(
    object,
    propertySelector
) {
    if (
        object === null ||
        object === undefined ||
        object.isNull()
    ) {
        return null;
    }

    try {
        return stringValue(
            objcMsgSendPointer(
                object,
                propertySelector
            )
        );

    } catch (error) {
        return null;
    }
}


function stack(context) {
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


function methodImplementation(
    classNameValue,
    selectorNameValue
) {
    const klass =
        objcGetClass(
            Memory.allocUtf8String(
                classNameValue
            )
        );

    if (klass.isNull()) {
        throw new Error(
            classNameValue
            + ' unavailable'
        );
    }

    const method =
        classGetInstanceMethod(
            klass,
            selector(
                selectorNameValue
            )
        );

    if (method.isNull()) {
        throw new Error(
            selectorNameValue
            + ' unavailable'
        );
    }

    return methodGetImplementation(
        method
    );
}


let sequence = 0;


const presentImplementation =
    methodImplementation(
        'UIViewController',
        'presentViewController:'
        + 'animated:'
        + 'completion:'
    );


Interceptor.attach(
    presentImplementation,
    {
        onEnter(args) {
            sequence += 1;

            const presenter =
                args[0];

            const presented =
                args[2];

            send({
                event:
                    'presentation',

                sequence:
                    sequence,

                presenterClass:
                    className(
                        presenter
                    ),

                presenterTitle:
                    stringProperty(
                        presenter,
                        titleSelector
                    ),

                presentedClass:
                    className(
                        presented
                    ),

                presentedTitle:
                    stringProperty(
                        presented,
                        titleSelector
                    ),

                presentedAccessibilityIdentifier:
                    stringProperty(
                        presented,
                        accessibilityIdentifierSelector
                    ),

                animated:
                    !args[3].isNull()
                    && args[3].toInt32() !== 0,

                presenter:
                    presenter.toString(),

                presented:
                    presented.toString(),

                stack:
                    stack(
                        this.context
                    )
            });
        }
    }
);


send({
    event:
        'ready',

    pid:
        Process.id
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
                json.dumps(record)
                + "\n"
            )

            output.flush()

            event = record.get(
                "event"
            )

            if event == "ready":
                ready.set()

            elif event == "presentation":
                log("")
                log(
                    "PRESENTATION "
                    + str(
                        record.get(
                            "sequence"
                        )
                    )
                )

                log(
                    "  presenter: "
                    + str(
                        record.get(
                            "presenterClass"
                        )
                    )
                )

                log(
                    "  presented: "
                    + str(
                        record.get(
                            "presentedClass"
                        )
                    )
                )

                log(
                    "  title:     "
                    + str(
                        record.get(
                            "presentedTitle"
                        )
                    )
                )

                log(
                    "  top stack:"
                )

                for frame in (
                    record.get("stack")
                    or []
                )[:10]:
                    log(
                        "    "
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
        "Tap only Music's native "
        "AirPlay button once."
    )

    log(
        "When the picker appears, "
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
