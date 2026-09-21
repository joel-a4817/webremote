#!/usr/bin/env python3

import json
import signal
import sys
import threading
from pathlib import Path

import frida


OUTPUT = (
    Path(__file__).resolve().parent
    / "main-music-picker-actions.jsonl"
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


const selGetName =
    new NativeFunction(
        globalExport(
            'sel_getName'
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


const utf8StringSelector =
    selector(
        'UTF8String'
    );


const accessibilityLabelSelector =
    selector(
        'accessibilityLabel'
    );


const accessibilityIdentifierSelector =
    selector(
        'accessibilityIdentifier'
    );


const titleSelector =
    selector(
        'currentTitle'
    );


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
            objectGetClass(
                object
            );

        if (klass.isNull()) {
            return null;
        }

        const namePointer =
            classGetName(
                klass
            );

        if (namePointer.isNull()) {
            return null;
        }

        return namePointer
            .readUtf8String();

    } catch (error) {
        return null;
    }
}


function selectorName(value) {
    if (
        value === null ||
        value === undefined ||
        value.isNull()
    ) {
        return null;
    }

    try {
        const pointer =
            selGetName(
                value
            );

        if (pointer.isNull()) {
            return null;
        }

        return pointer
            .readUtf8String();

    } catch (error) {
        return null;
    }
}


function stringFromNSString(
    value
) {
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

        if (pointer.isNull()) {
            return null;
        }

        return pointer
            .readUtf8String();

    } catch (error) {
        return null;
    }
}


function objectStringProperty(
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
        const value =
            objcMsgSendPointer(
                object,
                propertySelector
            );

        return stringFromNSString(
            value
        );

    } catch (error) {
        return null;
    }
}


function senderMetadata(sender) {
    return {
        class:
            className(sender),

        accessibilityLabel:
            objectStringProperty(
                sender,
                accessibilityLabelSelector
            ),

        accessibilityIdentifier:
            objectStringProperty(
                sender,
                accessibilityIdentifierSelector
            ),

        currentTitle:
            objectStringProperty(
                sender,
                titleSelector
            )
    };
}


function backtrace(context) {
    try {
        return Thread.backtrace(
            context,
            Backtracer.ACCURATE
        ).map(address => {
            const symbol =
                DebugSymbol
                    .fromAddress(
                        address
                    );

            return {
                address:
                    address.toString(),

                symbol:
                    symbol.toString()
            };
        });

    } catch (error) {
        return [{
            error:
                String(error)
        }];
    }
}


function findImplementation(
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
            + ' class unavailable'
        );
    }

    const targetSelector =
        selector(
            selectorNameValue
        );

    const method =
        classGetInstanceMethod(
            klass,
            targetSelector
        );

    if (method.isNull()) {
        throw new Error(
            classNameValue
            + ' '
            + selectorNameValue
            + ' unavailable'
        );
    }

    return methodGetImplementation(
        method
    );
}


let sequence = 0;


function emitAction(
    source,
    action,
    target,
    sender,
    context
) {
    sequence += 1;

    send({
        event:
            'action',

        sequence:
            sequence,

        timestamp:
            new Date()
                .toISOString(),

        source:
            source,

        action:
            selectorName(
                action
            ),

        targetClass:
            className(
                target
            ),

        sender:
            senderMetadata(
                sender
            ),

        stack:
            backtrace(
                context
            )
    });
}


/*
 * Highest-value hook:
 *
 * -[UIApplication
 *   sendAction:to:from:forEvent:]
 *
 * This is the final UIKit action dispatch path and
 * exposes the action selector, target, and sender.
 */
const applicationSendAction =
    findImplementation(
        'UIApplication',
        'sendAction:to:from:forEvent:'
    );


Interceptor.attach(
    applicationSendAction,
    {
        onEnter(args) {
            emitAction(
                'UIApplication',
                args[2],
                args[3],
                args[4],
                this.context
            );
        }
    }
);


/*
 * Also capture UIControl dispatch. This can reveal
 * the sender-side selector before UIApplication
 * resolves a nil target through the responder chain.
 */
const controlSendAction =
    findImplementation(
        'UIControl',
        'sendAction:to:forEvent:'
    );


Interceptor.attach(
    controlSendAction,
    {
        onEnter(args) {
            emitAction(
                'UIControl',
                args[2],
                args[3],
                args[0],
                this.context
            );
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


def log(text):
    print(
        text,
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
            == "Music"
        ),
        None,
    )

    if process is None:
        raise RuntimeError(
            "Music is not running. "
            "Open Music and open its AirPlay "
            "picker once, then rerun."
        )

    log(
        "Attaching to Music "
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

            elif event == "action":
                sender = (
                    record.get("sender")
                    or {}
                )

                log("")
                log(
                    "ACTION "
                    + str(
                        record.get("sequence")
                    )
                )

                log(
                    "  selector: "
                    + str(
                        record.get("action")
                    )
                )

                log(
                    "  target:   "
                    + str(
                        record.get(
                            "targetClass"
                        )
                    )
                )

                log(
                    "  sender:   "
                    + str(
                        sender.get("class")
                    )
                )

                log(
                    "  label:    "
                    + str(
                        sender.get(
                            "accessibilityLabel"
                        )
                    )
                )

                log(
                    "  id:       "
                    + str(
                        sender.get(
                            "accessibilityIdentifier"
                        )
                    )
                )

                log(
                    "  title:    "
                    + str(
                        sender.get(
                            "currentTitle"
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
            "Frida hook did not become ready"
        )

    log("")
    log(
        "Capture armed."
    )

    log(
        "Now tap ONLY Music's native "
        "AirPlay button once."
    )

    log(
        "Wait until its picker appears, "
        "then press Ctrl+C here."
    )

    while not stop_event.wait(
        0.25
    ):
        pass

    log(
        "Detaching..."
    )

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
