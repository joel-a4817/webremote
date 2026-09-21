
'use strict';


if (!ObjC.available) {
    throw new Error(
        'Objective-C runtime unavailable'
    );
}


const MPRouteButton =
    ObjC.classes.MPRouteButton;


if (MPRouteButton === undefined) {
    throw new Error(
        'MPRouteButton unavailable'
    );
}


function safeObject(value) {
    try {
        if (
            value === null
            || value === undefined
        ) {
            return null;
        }

        return value.toString();

    } catch (error) {
        return null;
    }
}


function safeClassName(object) {
    try {
        return object.$className;

    } catch (error) {
        return null;
    }
}


function describeButton(button) {
    let window = null;
    let superview = null;
    let targets = null;
    let touchUpInsideActions = null;
    let primaryActions = null;

    try {
        window = button.window();

    } catch (error) {
    }

    try {
        superview = button.superview();

    } catch (error) {
    }

    try {
        targets = button.allTargets();

    } catch (error) {
    }

    try {
        touchUpInsideActions =
            button.actionsForTarget_forControlEvent_(
                null,
                64
            );

    } catch (error) {
    }

    /*
     * UIControlEventPrimaryActionTriggered
     * is 1 << 13.
     */
    try {
        primaryActions =
            button.actionsForTarget_forControlEvent_(
                null,
                8192
            );

    } catch (error) {
    }

    return {
        pointer:
            button.handle.toString(),

        className:
            button.$className,

        window:
            window
                ? window.handle.toString()
                : null,

        windowClass:
            window
                ? safeClassName(window)
                : null,

        superview:
            superview
                ? superview.handle.toString()
                : null,

        superviewClass:
            superview
                ? safeClassName(superview)
                : null,

        hidden:
            Boolean(button.isHidden()),

        alpha:
            Number(button.alpha()),

        enabled:
            Boolean(button.isEnabled()),

        userInteractionEnabled:
            Boolean(
                button.isUserInteractionEnabled()
            ),

        targets:
            safeObject(targets),

        touchUpInsideActions:
            safeObject(
                touchUpInsideActions
            ),

        primaryActions:
            safeObject(
                primaryActions
            )
    };
}


ObjC.schedule(
    ObjC.mainQueue,
    function() {
        try {
            const candidates =
                ObjC.chooseSync(
                    MPRouteButton
                );

            const details =
                candidates.map(
                    describeButton
                );

            send({
                event:
                    'candidates',

                count:
                    candidates.length,

                buttons:
                    details
            });

            const button =
                candidates.find(
                    candidate => {
                        try {
                            return (
                                candidate.window()
                                !== null
                                &&
                                !candidate.isHidden()
                                &&
                                candidate.alpha() > 0.01
                                &&
                                candidate.isEnabled()
                            );

                        } catch (error) {
                            return false;
                        }
                    }
                );


            if (button === undefined) {
                send({
                    event:
                        'failed',

                    reason:
                        'No attached visible '
                        + 'MPRouteButton found'
                });

                return;
            }


            send({
                event:
                    'triggering',

                button:
                    describeButton(button)
            });


            /*
             * First reproduce the normal UIControl
             * touch-up-inside event.
             */
            button.sendActionsForControlEvents_(
                64
            );


            send({
                event:
                    'triggered',

                method:
                    'sendActionsForControlEvents:',

                controlEvents:
                    64
            });

        } catch (error) {
            send({
                event:
                    'failed',

                reason:
                    String(error),

                stack:
                    error.stack || null
            });
        }
    }
);

setInterval(
    function() {
    },
    1000
);
