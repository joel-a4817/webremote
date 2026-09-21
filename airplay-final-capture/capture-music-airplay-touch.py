#!/usr/bin/env python3

import json
import signal
import sys
import threading
from pathlib import Path

import frida


OUTPUT = (
    Path(__file__).resolve().parent
    / "music-airplay-touch.jsonl"
)

stop_event = threading.Event()


AGENT = r'''
'use strict';


function exported(name) {
    return Module.getGlobalExportByName(name);
}


const objcGetClass =
    new NativeFunction(
        exported('objc_getClass'),
        'pointer',
        ['pointer']
    );


const selRegisterName =
    new NativeFunction(
        exported('sel_registerName'),
        'pointer',
        ['pointer']
    );


const classGetInstanceMethod =
    new NativeFunction(
        exported('class_getInstanceMethod'),
        'pointer',
        ['pointer', 'pointer']
    );


const methodGetImplementation =
    new NativeFunction(
        exported('method_getImplementation'),
        'pointer',
        ['pointer']
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


const objcMsgSendPointer0 =
    new NativeFunction(
        exported('objc_msgSend'),
        'pointer',
        ['pointer', 'pointer']
    );


const objcMsgSendULong0 =
    new NativeFunction(
        exported('objc_msgSend'),
        'ulong',
        ['pointer', 'pointer']
    );


const objcMsgSendBool0 =
    new NativeFunction(
        exported('objc_msgSend'),
        'bool',
        ['pointer', 'pointer']
    );


function selector(name) {
    return selRegisterName(
        Memory.allocUtf8String(name)
    );
}


function getClass(name) {
    return objcGetClass(
        Memory.allocUtf8String(name)
    );
}


function className(object) {
    if (
        object === null
        || object === undefined
        || object.isNull()
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


function pointerProperty(
    object,
    selectorValue
) {
    if (
        object === null
        || object === undefined
        || object.isNull()
    ) {
        return ptr(0);
    }

    try {
        return objcMsgSendPointer0(
            object,
            selectorValue
        );

    } catch (error) {
        return ptr(0);
    }
}


function ulongProperty(
    object,
    selectorValue
) {
    if (
        object === null
        || object === undefined
        || object.isNull()
    ) {
        return null;
    }

    try {
        return Number(
            objcMsgSendULong0(
                object,
                selectorValue
            )
        );

    } catch (error) {
        return null;
    }
}


function boolProperty(
    object,
    selectorValue
) {
    if (
        object === null
        || object === undefined
        || object.isNull()
    ) {
        return null;
    }

    try {
        return Boolean(
            objcMsgSendBool0(
                object,
                selectorValue
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


function inspectObject(
    object,
    levels
) {
    const result = [];
    let current = object;

    for (
        let index = 0;
        index < levels;
        index++
    ) {
        if (
            current === null
            || current === undefined
            || current.isNull()
        ) {
            break;
        }

        result.push({
            pointer:
                current.toString(),

            className:
                className(current)
        });

        current =
            pointerProperty(
                current,
                superviewSelector
            );
    }

    return result;
}


function hookMethod(
    classNameValue,
    selectorNameValue,
    callback
) {
    const klass =
        getClass(
            classNameValue
        );

    if (klass.isNull()) {
        send({
            event:
                'missing-class',

            className:
                classNameValue
        });

        return false;
    }

    const selectorValue =
        selector(
            selectorNameValue
        );

    const method =
        classGetInstanceMethod(
            klass,
            selectorValue
        );

    if (method.isNull()) {
        send({
            event:
                'missing-method',

            className:
                classNameValue,

            selector:
                selectorNameValue
        });

        return false;
    }

    const implementation =
        methodGetImplementation(
            method
        );

    if (implementation.isNull()) {
        return false;
    }

    Interceptor.attach(
        implementation,
        callback
    );

    send({
        event:
            'hook-installed',

        className:
            classNameValue,

        selector:
            selectorNameValue,

        implementation:
            implementation.toString()
    });

    return true;
}


const allTouchesSelector =
    selector('allTouches');

const anyObjectSelector =
    selector('anyObject');

const phaseSelector =
    selector('phase');

const viewSelector =
    selector('view');

const windowSelector =
    selector('window');

const superviewSelector =
    selector('superview');

const gestureRecognizersSelector =
    selector('gestureRecognizers');

const countSelector =
    selector('count');

const enabledSelector =
    selector('isEnabled');

const stateSelector =
    selector('state');


hookMethod(
    'UIApplication',
    'sendEvent:',
    {
        onEnter(args) {
            const event =
                args[2];

            const touches =
                pointerProperty(
                    event,
                    allTouchesSelector
                );

            if (touches.isNull()) {
                return;
            }

            const touch =
                pointerProperty(
                    touches,
                    anyObjectSelector
                );

            if (touch.isNull()) {
                return;
            }

            const phase =
                ulongProperty(
                    touch,
                    phaseSelector
                );

            /*
             * UITouchPhaseEnded = 3.
             *
             * Only emit once when the manual tap
             * finishes, avoiding move-event noise.
             */
            if (phase !== 3) {
                return;
            }

            const view =
                pointerProperty(
                    touch,
                    viewSelector
                );

            const window =
                pointerProperty(
                    touch,
                    windowSelector
                );

            const recognizers =
                pointerProperty(
                    view,
                    gestureRecognizersSelector
                );

            send({
                event:
                    'touch-ended',

                touch:
                    touch.toString(),

                touchedView:
                    view.toString(),

                touchedViewClass:
                    className(view),

                window:
                    window.toString(),

                windowClass:
                    className(window),

                hierarchy:
                    inspectObject(
                        view,
                        15
                    ),

                gestureRecognizerCount:
                    recognizers.isNull()
                        ? 0
                        : ulongProperty(
                            recognizers,
                            countSelector
                        ),

                stack:
                    stack(
                        this.context
                    )
            });
        }
    }
);


const gestureMethods = [
    '_sendActions',
    '_sendActionWithGestureRecognizer:',
    '_sendDelayedActions',
    '_updateGestureForActiveEvents'
];


for (
    const methodName
    of gestureMethods
) {
    hookMethod(
        'UIGestureRecognizer',
        methodName,
        {
            onEnter(args) {
                const recognizer =
                    args[0];

                const view =
                    pointerProperty(
                        recognizer,
                        viewSelector
                    );

                send({
                    event:
                        'gesture-dispatch',

                    selector:
                        methodName,

                    recognizer:
                        recognizer.toString(),

                    recognizerClass:
                        className(recognizer),

                    view:
                        view.toString(),

                    viewClass:
                        className(view),

                    enabled:
                        boolProperty(
                            recognizer,
                            enabledSelector
                        ),

                    state:
                        ulongProperty(
                            recognizer,
                            stateSelector
                        ),

                    hierarchy:
                        inspectObject(
                            view,
                            15
                        ),

                    stack:
                        stack(
                            this.context
                        )
                });
            }
        }
    );
}


hookMethod(
    'NSObject',
    'accessibilityActivate',
    {
        onEnter(args) {
            const object =
                args[0];

            const name =
                className(object)
                || '';

            const lower =
                name.toLowerCase();

            if (
                !lower.includes('music')
                && !lower.includes('player')
                && !lower.includes('route')
                && !lower.includes('button')
                && !lower.includes('swift')
            ) {
                return;
            }

            send({
                event:
                    'accessibility-activate',

                object:
                    object.toString(),

                className:
                    name,

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
            if item.name == "Music"
        ),
        None,
    )

    if process is None:
        raise RuntimeError(
            "Music is not running"
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
        if message.get("type") == "send":
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

            event = record.get("event")

            if event == "ready":
                ready.set()

            elif event == "hook-installed":
                log(
                    "HOOK "
                    + str(
                        record.get("className")
                    )
                    + " "
                    + str(
                        record.get("selector")
                    )
                )

            elif event == "missing-method":
                log(
                    "SKIP "
                    + str(
                        record.get("className")
                    )
                    + " "
                    + str(
                        record.get("selector")
                    )
                )

            elif event == "touch-ended":
                log("")
                log(
                    "TOUCH ENDED on "
                    + str(
                        record.get(
                            "touchedViewClass"
                        )
                    )
                    + " "
                    + str(
                        record.get(
                            "touchedView"
                        )
                    )
                )

                log(
                    "Hierarchy:"
                )

                for item in record.get(
                    "hierarchy",
                    [],
                ):
                    log(
                        "  "
                        + str(
                            item.get("className")
                        )
                        + " "
                        + str(
                            item.get("pointer")
                        )
                    )

            elif event == "gesture-dispatch":
                log("")
                log(
                    "GESTURE "
                    + str(
                        record.get(
                            "recognizerClass"
                        )
                    )
                    + " "
                    + str(
                        record.get("selector")
                    )
                )

                log(
                    "  view: "
                    + str(
                        record.get("viewClass")
                    )
                    + " "
                    + str(
                        record.get("view")
                    )
                )

                log(
                    "  state: "
                    + str(
                        record.get("state")
                    )
                )

                log(
                    "  top stack:"
                )

                for frame in (
                    record.get("stack")
                    or []
                )[:12]:
                    log(
                        "    "
                        + str(
                            frame.get("symbol")
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
            "Capture did not become ready"
        )

    log("")
    log(
        "Capture armed in Music."
    )

    log(
        "Tap only the visible AirPlay button once."
    )

    log(
        "After the native picker appears, "
        "press Ctrl+C."
    )

    while not stop_event.wait(0.25):
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
