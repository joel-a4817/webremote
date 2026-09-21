#!/usr/bin/env python3

import json
import signal
import sys
import threading
from pathlib import Path

import frida


OUTPUT = (
    Path(__file__).resolve().parent
    / "music-route-picker-calls.jsonl"
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
        [
            'pointer',
            'pointer'
        ]
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


const objcMsgSendPointer =
    new NativeFunction(
        exported('objc_msgSend'),
        'pointer',
        [
            'pointer',
            'pointer'
        ]
    );


const objcMsgSendDouble =
    new NativeFunction(
        exported('objc_msgSend'),
        'double',
        [
            'pointer',
            'pointer'
        ]
    );


const objcMsgSendBool =
    new NativeFunction(
        exported('objc_msgSend'),
        'bool',
        [
            'pointer',
            'pointer'
        ]
    );


function selector(name) {
    return selRegisterName(
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


function callPointer(
    object,
    selectorValue
) {
    try {
        return objcMsgSendPointer(
            object,
            selectorValue
        );

    } catch (error) {
        return ptr(0);
    }
}


function callBool(
    object,
    selectorValue
) {
    try {
        return Boolean(
            objcMsgSendBool(
                object,
                selectorValue
            )
        );

    } catch (error) {
        return null;
    }
}


function callDouble(
    object,
    selectorValue
) {
    try {
        return Number(
            objcMsgSendDouble(
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


const windowSelector =
    selector('window');

const hiddenSelector =
    selector('isHidden');

const alphaSelector =
    selector('alpha');

const superviewSelector =
    selector('superview');

const customButtonSelector =
    selector('customButton');

const routingConfigurationSelector =
    selector('routingConfiguration');

const playerSelector =
    selector('player');


const routePickerClass =
    objcGetClass(
        Memory.allocUtf8String(
            'AVRoutePickerView'
        )
    );


if (routePickerClass.isNull()) {
    throw new Error(
        'AVRoutePickerView is not loaded '
        + 'in the Music process'
    );
}


const targets = [
    '_routePickerButtonTapped:',
    'presentRoutePicker:',
    '_routePickerButtonTouchDown:',
    '_routePickerButtonTouchUp:',
    '_setupOutputContext',
    '_createOrUpdateRoutePickerButton'
];


const installed = [];


for (
    const selectorName
    of targets
) {
    const selectorValue =
        selector(selectorName);

    const method =
        classGetInstanceMethod(
            routePickerClass,
            selectorValue
        );

    if (method.isNull()) {
        send({
            event:
                'missing-selector',

            selector:
                selectorName
        });

        continue;
    }

    const implementation =
        methodGetImplementation(method);

    if (implementation.isNull()) {
        continue;
    }

    Interceptor.attach(
        implementation,
        {
            onEnter(args) {
                const receiver =
                    args[0];

                const window =
                    callPointer(
                        receiver,
                        windowSelector
                    );

                const superview =
                    callPointer(
                        receiver,
                        superviewSelector
                    );

                const customButton =
                    callPointer(
                        receiver,
                        customButtonSelector
                    );

                const routingConfiguration =
                    callPointer(
                        receiver,
                        routingConfigurationSelector
                    );

                const player =
                    callPointer(
                        receiver,
                        playerSelector
                    );

                send({
                    event:
                        'picker-call',

                    timestamp:
                        new Date()
                            .toISOString(),

                    selector:
                        selectorName,

                    receiver:
                        receiver.toString(),

                    receiverClass:
                        className(receiver),

                    argument:
                        args[2].toString(),

                    window:
                        window.toString(),

                    windowClass:
                        className(window),

                    superview:
                        superview.toString(),

                    superviewClass:
                        className(superview),

                    customButton:
                        customButton.toString(),

                    customButtonClass:
                        className(customButton),

                    routingConfiguration:
                        routingConfiguration.toString(),

                    routingConfigurationClass:
                        className(
                            routingConfiguration
                        ),

                    player:
                        player.toString(),

                    playerClass:
                        className(player),

                    hidden:
                        callBool(
                            receiver,
                            hiddenSelector
                        ),

                    alpha:
                        callDouble(
                            receiver,
                            alphaSelector
                        ),

                    stack:
                        stack(
                            this.context
                        )
                });
            }
        }
    );

    installed.push({
        selector:
            selectorName,

        implementation:
            implementation.toString()
    });
}


send({
    event:
        'ready',

    pid:
        Process.id,

    installed:
        installed
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
            "Music is not running. Open it with "
            "music://show-now-playing first."
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

                log(
                    "Installed exact hooks:"
                )

                for item in record.get(
                    "installed",
                    [],
                ):
                    log(
                        "  "
                        + item["selector"]
                        + " @ "
                        + item["implementation"]
                    )

            elif event == "missing-selector":
                log(
                    "Missing selector: "
                    + str(
                        record.get("selector")
                    )
                )

            elif event == "picker-call":
                log("")
                log(
                    "CALL "
                    + str(
                        record.get("selector")
                    )
                )

                log(
                    "  self:    "
                    + str(
                        record.get("receiver")
                    )
                )

                log(
                    "  window:  "
                    + str(
                        record.get("windowClass")
                    )
                    + " "
                    + str(
                        record.get("window")
                    )
                )

                log(
                    "  parent:  "
                    + str(
                        record.get("superviewClass")
                    )
                )

                log(
                    "  button:  "
                    + str(
                        record.get(
                            "customButtonClass"
                        )
                    )
                )

                log(
                    "  config:  "
                    + str(
                        record.get(
                            "routingConfigurationClass"
                        )
                    )
                )

                log(
                    "  player:  "
                    + str(
                        record.get("playerClass")
                    )
                )

                log(
                    "  hidden:  "
                    + str(
                        record.get("hidden")
                    )
                )

                log(
                    "  alpha:   "
                    + str(
                        record.get("alpha")
                    )
                )

                log(
                    "  top stack:"
                )

                for frame in (
                    record.get("stack")
                    or []
                )[:15]:
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
            "Hook did not become ready"
        )

    log("")
    log(
        "Capture armed in the Music process."
    )

    log(
        "Manually tap Music's AirPlay button once."
    )

    log(
        "After the picker appears, press Ctrl+C."
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
