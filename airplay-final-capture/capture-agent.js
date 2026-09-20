'use strict';

const getExport = name =>
    Module.getGlobalExportByName(name);

const dictionaryGetData =
    new NativeFunction(
        getExport(
            'xpc_dictionary_get_data'
        ),
        'pointer',
        [
            'pointer',
            'pointer',
            'pointer'
        ]
    );

const dictionaryGetString =
    new NativeFunction(
        getExport(
            'xpc_dictionary_get_string'
        ),
        'pointer',
        [
            'pointer',
            'pointer'
        ]
    );

const dictionaryGetUInt64 =
    new NativeFunction(
        getExport(
            'xpc_dictionary_get_uint64'
        ),
        'uint64',
        [
            'pointer',
            'pointer'
        ]
    );

const copyDescription =
    new NativeFunction(
        getExport(
            'xpc_copy_description'
        ),
        'pointer',
        ['pointer']
    );

const freeMemory =
    new NativeFunction(
        getExport('free'),
        'void',
        ['pointer']
    );

const keyModificationData =
    Memory.allocUtf8String(
        'MRXPC_CONTEXT_MODIFICATION_DATA_KEY'
    );

const keyRoutingContext =
    Memory.allocUtf8String(
        'MRXPC_ROUTING_CONTEXT_UID_KEY'
    );

const keyMessageID =
    Memory.allocUtf8String(
        'MRXPC_MESSAGE_ID_KEY'
    );

const keyCustomID =
    Memory.allocUtf8String(
        'MRXPC_MESSAGE_CUSTOM_ID_KEY'
    );

function describeXPC(object) {
    if (
        object === null ||
        object === undefined ||
        object.isNull()
    ) {
        return null;
    }

    try {
        const pointer =
            copyDescription(object);

        if (pointer.isNull()) {
            return null;
        }

        let result = null;

        try {
            result =
                pointer.readUtf8String();
        } finally {
            freeMemory(pointer);
        }

        return result;
    } catch (error) {
        return (
            '<description error: '
            + String(error)
            + '>'
        );
    }
}

function readString(
    dictionary,
    key
) {
    try {
        const value =
            dictionaryGetString(
                dictionary,
                key
            );

        if (value.isNull()) {
            return null;
        }

        return value.readUtf8String();
    } catch (error) {
        return null;
    }
}

function readUInt64(
    dictionary,
    key
) {
    try {
        return dictionaryGetUInt64(
            dictionary,
            key
        ).toString();
    } catch (error) {
        return null;
    }
}

function bytesToHex(
    pointer,
    length
) {
    const buffer =
        pointer.readByteArray(length);

    if (buffer === null) {
        return '';
    }

    const bytes =
        new Uint8Array(buffer);

    let result = '';

    for (
        let index = 0;
        index < bytes.length;
        index++
    ) {
        result += bytes[index]
            .toString(16)
            .padStart(2, '0');
    }

    return result;
}

function readModificationData(
    message
) {
    const lengthPointer =
        Memory.alloc(
            Process.pointerSize
        );

    if (Process.pointerSize === 8) {
        lengthPointer.writeU64(0);
    } else {
        lengthPointer.writeU32(0);
    }

    try {
        const dataPointer =
            dictionaryGetData(
                message,
                keyModificationData,
                lengthPointer
            );

        const length =
            Process.pointerSize === 8
                ? Number(
                    lengthPointer.readU64()
                )
                : lengthPointer.readU32();

        if (
            dataPointer.isNull() ||
            length === 0
        ) {
            return null;
        }

        return {
            length: length,
            hex:
                bytesToHex(
                    dataPointer,
                    length
                )
        };
    } catch (error) {
        return null;
    }
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
            error: String(error)
        }];
    }
}

let captured = false;

function install(
    exportName
) {
    let implementation = null;

    try {
        implementation =
            getExport(exportName);
    } catch (error) {
        send({
            event: 'hook-unavailable',
            api: exportName,
            error: String(error)
        });

        return;
    }

    Interceptor.attach(
        implementation,
        {
            onEnter(args) {
                if (captured) {
                    return;
                }

                const message =
                    args[1];

                if (
                    message === null ||
                    message.isNull()
                ) {
                    return;
                }

                const modificationData =
                    readModificationData(
                        message
                    );

                if (
                    modificationData === null
                ) {
                    return;
                }

                captured = true;

                send({
                    event:
                        'outbound-airplay-request',
                    timestamp:
                        new Date().toISOString(),
                    pid: Process.id,
                    threadID:
                        Process
                            .getCurrentThreadId(),
                    api: exportName,
                    connection:
                        describeXPC(args[0]),
                    message:
                        describeXPC(message),
                    messageID:
                        readUInt64(
                            message,
                            keyMessageID
                        ),
                    customID:
                        readString(
                            message,
                            keyCustomID
                        ),
                    routingContextUID:
                        readString(
                            message,
                            keyRoutingContext
                        ),
                    modificationData:
                        modificationData,
                    stack:
                        captureStack(
                            this.context
                        )
                });
            }
        }
    );

    send({
        event: 'hook-installed',
        api: exportName,
        implementation:
            implementation.toString()
    });
}

install(
    'xpc_connection_send_message'
);

install(
    'xpc_connection_send_message_with_reply'
);

install(
    'xpc_connection_send_message_with_reply_sync'
);

send({
    event: 'ready',
    pid: Process.id
});
