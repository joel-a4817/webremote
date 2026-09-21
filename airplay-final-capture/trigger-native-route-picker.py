#!/usr/bin/env python3

import json
import sys
import threading

import frida


AGENT = r'''
'use strict';

function exp(name) {
    return Module.getGlobalExportByName(name);
}

const objcGetClass = new NativeFunction(
    exp('objc_getClass'),
    'pointer',
    ['pointer']
);

const selRegisterName = new NativeFunction(
    exp('sel_registerName'),
    'pointer',
    ['pointer']
);

const objcMsgSend0 = new NativeFunction(
    exp('objc_msgSend'),
    'pointer',
    ['pointer', 'pointer']
);

const objcMsgSend1 = new NativeFunction(
    exp('objc_msgSend'),
    'pointer',
    ['pointer', 'pointer', 'pointer']
);

const objcMsgSendIndex = new NativeFunction(
    exp('objc_msgSend'),
    'pointer',
    ['pointer', 'pointer', 'ulong']
);

const objcMsgSendULong = new NativeFunction(
    exp('objc_msgSend'),
    'ulong',
    ['pointer', 'pointer']
);

const objcMsgSendVoidObject = new NativeFunction(
    exp('objc_msgSend'),
    'void',
    ['pointer', 'pointer', 'pointer']
);

const objcMsgSendVoidULong = new NativeFunction(
    exp('objc_msgSend'),
    'void',
    ['pointer', 'pointer', 'ulong']
);

const objectGetClass = new NativeFunction(
    exp('object_getClass'),
    'pointer',
    ['pointer']
);

const classGetName = new NativeFunction(
    exp('class_getName'),
    'pointer',
    ['pointer']
);

const dispatchGetMainQueue = new NativeFunction(
    exp('dispatch_get_main_queue'),
    'pointer',
    []
);

const dispatchAsyncF = new NativeFunction(
    exp('dispatch_async_f'),
    'void',
    ['pointer', 'pointer', 'pointer']
);

function sel(name) {
    return selRegisterName(
        Memory.allocUtf8String(name)
    );
}

function cls(name) {
    return objcGetClass(
        Memory.allocUtf8String(name)
    );
}

function className(object) {
    if (object.isNull()) {
        return null;
    }

    const klass = objectGetClass(object);

    if (klass.isNull()) {
        return null;
    }

    const result = classGetName(klass);

    return result.isNull()
        ? null
        : result.readUtf8String();
}

const allocSel = sel('alloc');
const initSel = sel('init');
const sharedApplicationSel =
    sel('sharedApplication');
const keyWindowSel = sel('keyWindow');
const windowsSel = sel('windows');
const countSel = sel('count');
const objectAtIndexSel =
    sel('objectAtIndex:');
const addSubviewSel =
    sel('addSubview:');
const subviewsSel = sel('subviews');
const sendActionsSel =
    sel('sendActionsForControlEvents:');
const isKindOfClassSel =
    sel('isKindOfClass:');

const uiApplicationClass =
    cls('UIApplication');

const routePickerClass =
    cls('AVRoutePickerView');

const uiControlClass =
    cls('UIControl');

if (uiApplicationClass.isNull()) {
    throw new Error(
        'UIApplication unavailable'
    );
}

if (routePickerClass.isNull()) {
    throw new Error(
        'AVRoutePickerView unavailable'
    );
}

if (uiControlClass.isNull()) {
    throw new Error(
        'UIControl unavailable'
    );
}

function isUIControl(object) {
    if (object.isNull()) {
        return false;
    }

    return !objcMsgSend1(
        object,
        isKindOfClassSel,
        uiControlClass
    ).isNull();
}

function findControl(view, depth) {
    if (view.isNull() || depth > 10) {
        return ptr(0);
    }

    if (isUIControl(view)) {
        return view;
    }

    const subviews =
        objcMsgSend0(
            view,
            subviewsSel
        );

    if (subviews.isNull()) {
        return ptr(0);
    }

    const count = Number(
        objcMsgSendULong(
            subviews,
            countSel
        )
    );

    for (
        let index = 0;
        index < count;
        index++
    ) {
        const child =
            objcMsgSendIndex(
                subviews,
                objectAtIndexSel,
                index
            );

        const result =
            findControl(
                child,
                depth + 1
            );

        if (!result.isNull()) {
            return result;
        }
    }

    return ptr(0);
}

/*
 * Keep these references alive after the callback.
 */
let retainedPicker = ptr(0);
let retainedCallback = null;

retainedCallback = new NativeCallback(
    function(context) {
        try {
            const application =
                objcMsgSend0(
                    uiApplicationClass,
                    sharedApplicationSel
                );

            if (application.isNull()) {
                throw new Error(
                    'UIApplication sharedApplication failed'
                );
            }

            let window =
                objcMsgSend0(
                    application,
                    keyWindowSel
                );

            if (window.isNull()) {
                const windows =
                    objcMsgSend0(
                        application,
                        windowsSel
                    );

                const count = Number(
                    objcMsgSendULong(
                        windows,
                        countSel
                    )
                );

                if (count > 0) {
                    window =
                        objcMsgSendIndex(
                            windows,
                            objectAtIndexSel,
                            0
                        );
                }
            }

            if (window.isNull()) {
                throw new Error(
                    'No MusicUIService window'
                );
            }

            const allocated =
                objcMsgSend0(
                    routePickerClass,
                    allocSel
                );

            const picker =
                objcMsgSend0(
                    allocated,
                    initSel
                );

            if (picker.isNull()) {
                throw new Error(
                    'AVRoutePickerView init failed'
                );
            }

            retainedPicker = picker;

            objcMsgSendVoidObject(
                window,
                addSubviewSel,
                picker
            );

            const control =
                findControl(
                    picker,
                    0
                );

            if (control.isNull()) {
                throw new Error(
                    'No UIControl inside AVRoutePickerView'
                );
            }

            send({
                event: 'triggering',
                windowClass:
                    className(window),
                pickerClass:
                    className(picker),
                controlClass:
                    className(control)
            });

            /*
             * UIControlEventTouchUpInside.
             */
            objcMsgSendVoidULong(
                control,
                sendActionsSel,
                64
            );

            send({
                event: 'triggered'
            });

        } catch (error) {
            send({
                event: 'failed',
                error: String(error),
                stack:
                    error.stack || null
            });
        }
    },
    'void',
    ['pointer']
);

dispatchAsyncF(
    dispatchGetMainQueue(),
    ptr(0),
    retainedCallback
);

send({
    event: 'scheduled-on-main-thread'
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
            if item.name == "MusicUIService"
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

    complete = threading.Event()
    failed = False

    def on_message(message, data):
        nonlocal failed

        if message.get("type") == "send":
            payload = (
                message.get("payload")
                or {}
            )

            print(
                json.dumps(
                    payload,
                    indent=2,
                ),
                flush=True,
            )

            if payload.get("event") == "failed":
                failed = True
                complete.set()

            elif payload.get("event") == "triggered":
                complete.set()

        else:
            failed = True

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

    if not complete.wait(10):
        failed = True
        print(
            "ERROR: trigger timed out",
            flush=True,
        )

    # Keep the injected picker alive briefly.
    threading.Event().wait(3)

    script.unload()
    session.detach()

    if failed:
        raise RuntimeError(
            "Native route-picker trigger failed"
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
