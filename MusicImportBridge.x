#import <AVFoundation/AVFoundation.h>
#import <Foundation/Foundation.h>
#import <CoreFoundation/CoreFoundation.h>
#import <MediaPlayer/MediaPlayer.h>
#import <objc/message.h>
#import <unistd.h>

static NSString *const RequestPath =
    @"/var/mobile/MediaCtlMusicImport-request.plist";
static NSString *const ResponsePath =
    @"/var/mobile/MediaCtlMusicImport-response.plist";
static NSString *const DestinationDirectory =
    @"/var/mobile/Media/iTunes_Control/Music/Filza";
static CFStringRef const RequestNotification =
    CFSTR("com.joel.mediactl.music-import-request");
static CFStringRef const ResponseNotification =
    CFSTR("com.joel.mediactl.music-import-response");


static void writeResponse(NSDictionary *values) {
    NSMutableDictionary *response =
        [NSMutableDictionary dictionaryWithDictionary:values ?: @{}];
    response[@"updated"] = @([[NSDate date] timeIntervalSince1970]);
    [response writeToFile:ResponsePath atomically:YES];
    CFNotificationCenterPostNotification(
        CFNotificationCenterGetDarwinNotifyCenter(),
        ResponseNotification,
        NULL,
        NULL,
        true
    );
}

static BOOL validSourcePath(NSString *path) {
    if (![path isKindOfClass:[NSString class]] || path.length == 0) return NO;
    NSString *standardized = path.stringByStandardizingPath;
    if (![standardized hasPrefix:@"/var/mobile/Media/MusicUploads/"]) return NO;
    NSSet *allowed = [NSSet setWithArray:@[@"m4a", @"mp3", @"aac", @"alac", @"wav"]];
    if (![allowed containsObject:standardized.pathExtension.lowercaseString]) return NO;
    BOOL directory = NO;
    return [[NSFileManager defaultManager] fileExistsAtPath:standardized isDirectory:&directory] && !directory;
}

static NSString *uniquePath(NSString *directory, NSString *filename) {
    NSFileManager *fm = [NSFileManager defaultManager];
    NSString *candidate = [directory stringByAppendingPathComponent:filename];
    if (![fm fileExistsAtPath:candidate]) return candidate;
    NSString *stem = filename.stringByDeletingPathExtension;
    NSString *extension = filename.pathExtension;
    for (NSUInteger index = 2; index < 10000; index++) {
        NSString *next = extension.length > 0
            ? [NSString stringWithFormat:@"%@ %lu.%@", stem, (unsigned long)index, extension]
            : [NSString stringWithFormat:@"%@ %lu", stem, (unsigned long)index];
        candidate = [directory stringByAppendingPathComponent:next];
        if (![fm fileExistsAtPath:candidate]) return candidate;
    }
    return nil;
}

static NSString *uniqueImportPath(NSString *sourcePath) {
    NSString *name = [NSString stringWithFormat:@"%u.%@",
        arc4random_uniform(UINT32_MAX), sourcePath.pathExtension.lowercaseString];
    return uniquePath(DestinationDirectory, name);
}

static NSData *normalizedArtworkData(id value) {
    if ([value isKindOfClass:[NSData class]]) return value;
    if ([value isKindOfClass:[NSDictionary class]]) {
        id data = value[@"data"];
        if ([data isKindOfClass:[NSData class]]) return data;
    }
    return nil;
}

static NSDictionary *metadataForAudioFile(NSString *path, NSString *fallbackTitle) {
    AVURLAsset *asset = [AVURLAsset URLAssetWithURL:[NSURL fileURLWithPath:path] options:nil];
    dispatch_semaphore_t semaphore = dispatch_semaphore_create(0);
    __block NSArray<AVMetadataItem *> *metadata = nil;
    [asset loadValuesAsynchronouslyForKeys:@[@"commonMetadata"] completionHandler:^{
        NSError *error = nil;
        if ([asset statusOfValueForKey:@"commonMetadata" error:&error] == AVKeyValueStatusLoaded) {
            metadata = asset.commonMetadata;
        }
        dispatch_semaphore_signal(semaphore);
    }];
    long waitResult = dispatch_semaphore_wait(
        semaphore,
        dispatch_time(
            DISPATCH_TIME_NOW,
            15 * NSEC_PER_SEC
        )
    );

    if (waitResult != 0) {
        metadata = nil;
    }

    NSString *title = fallbackTitle ?: @"";
    NSString *artist = @"";
    NSString *album = @"";
    NSData *artwork = nil;
    for (AVMetadataItem *item in metadata ?: @[]) {
        if ([item.commonKey isEqualToString:AVMetadataCommonKeyTitle] &&
            [item.value isKindOfClass:[NSString class]] && [(NSString *)item.value length] > 0) {
            title = (NSString *)item.value;
        } else if ([item.commonKey isEqualToString:AVMetadataCommonKeyArtist] && [item.value isKindOfClass:[NSString class]]) {
            artist = (NSString *)item.value;
        } else if ([item.commonKey isEqualToString:AVMetadataCommonKeyAlbumName] && [item.value isKindOfClass:[NSString class]]) {
            album = (NSString *)item.value;
        } else if ([item.commonKey isEqualToString:AVMetadataCommonKeyArtwork]) {
            artwork = normalizedArtworkData(item.value);
        }
    }
    if (title.length == 0) title = path.lastPathComponent.stringByDeletingPathExtension;
    return @{@"title": title, @"artist": artist ?: @"", @"album": album ?: @"", @"artworkData": artwork ?: [NSNull null]};
}

static long long invokeFilzaImporter(NSString *path, NSString *title, NSData *artwork) {
    Class importerClass = NSClassFromString(@"TGMusicImporter");
    SEL shared = NSSelectorFromString(@"sharedInstance");
    SEL import = NSSelectorFromString(@"importLibraryItemFromFilePath:title:artworkData:");
    if (importerClass == Nil || ![importerClass respondsToSelector:shared]) return 0;
    id importer = ((id (*)(id, SEL))objc_msgSend)(importerClass, shared);
    if (importer == nil || ![importer respondsToSelector:import]) return 0;
    return ((long long (*)(id, SEL, NSString *, NSString *, NSData *))objc_msgSend)(
        importer, import, path, title, artwork
    );
}


static void processImport(NSDictionary *request, NSString *requestID) {
    NSString *source = request[@"sourcePath"];
    NSString *requestedTitle = request[@"title"];
    if (!validSourcePath(source)) {
        writeResponse(@{@"requestID": requestID, @"action": @"import", @"ok": @NO,
            @"error": @"Invalid or missing source file"});
        return;
    }

    NSFileManager *fm = [NSFileManager defaultManager];
    NSError *error = nil;
    if (![fm createDirectoryAtPath:DestinationDirectory withIntermediateDirectories:YES attributes:nil error:&error]) {
        writeResponse(@{@"requestID": requestID, @"action": @"import", @"ok": @NO,
            @"error": error.localizedDescription ?: @"Could not create import directory"});
        return;
    }

    NSString *destination = uniqueImportPath(source);
    if (destination == nil || ![fm copyItemAtPath:source toPath:destination error:&error]) {
        writeResponse(@{@"requestID": requestID, @"action": @"import", @"ok": @NO,
            @"error": error.localizedDescription ?: @"Could not copy audio file"});
        return;
    }

    NSDictionary *metadata = metadataForAudioFile(destination, requestedTitle);
    NSData *artwork = [metadata[@"artworkData"] isKindOfClass:[NSData class]] ? metadata[@"artworkData"] : nil;
    long long persistentID = invokeFilzaImporter(destination, metadata[@"title"], artwork);
    if (persistentID == 0) {
        [fm removeItemAtPath:destination error:nil];
        writeResponse(@{@"requestID": requestID, @"action": @"import", @"ok": @NO,
            @"error": @"Filza importer returned no persistent ID"});
        return;
    }

    [fm removeItemAtPath:source error:nil];
    writeResponse(@{
        @"requestID": requestID, @"action": @"import", @"ok": @YES,
        @"persistentID": [NSString stringWithFormat:@"%llu", (unsigned long long)persistentID],
        @"destinationPath": destination, @"title": metadata[@"title"],
        @"artworkImported": @(artwork != nil), @"stagingRemoved": @YES, @"error": @""
    });
}

static NSDictionary *importResult(NSDictionary *request) {
    NSString *source = request[@"sourcePath"];
    NSString *requestedTitle = request[@"title"];
    NSString *filename = [request[@"filename"] isKindOfClass:[NSString class]]
        ? request[@"filename"] : source.lastPathComponent;
    if (!validSourcePath(source)) {
        return @{@"filename": filename ?: @"", @"ok": @NO,
            @"error": @"Invalid or missing source file"};
    }
    NSFileManager *fm = [NSFileManager defaultManager];
    NSError *error = nil;
    if (![fm createDirectoryAtPath:DestinationDirectory
        withIntermediateDirectories:YES attributes:nil error:&error]) {
        return @{@"filename": filename ?: @"", @"ok": @NO,
            @"error": error.localizedDescription ?: @"Could not create import directory"};
    }
    NSString *destination = uniqueImportPath(source);
    if (destination == nil || ![fm copyItemAtPath:source toPath:destination error:&error]) {
        return @{@"filename": filename ?: @"", @"ok": @NO,
            @"error": error.localizedDescription ?: @"Could not copy audio file"};
    }
    NSDictionary *metadata = metadataForAudioFile(destination, requestedTitle);
    NSData *artwork = [metadata[@"artworkData"] isKindOfClass:[NSData class]]
        ? metadata[@"artworkData"] : nil;
    long long persistentID = invokeFilzaImporter(destination, metadata[@"title"], artwork);
    if (persistentID == 0) {
        [fm removeItemAtPath:destination error:nil];
        return @{@"filename": filename ?: @"", @"ok": @NO,
            @"error": @"Filza importer returned no persistent ID"};
    }
    [fm removeItemAtPath:source error:nil];
    return @{
        @"filename": filename ?: @"", @"ok": @YES,
        @"persistentID": [NSString stringWithFormat:@"%llu", (unsigned long long)persistentID],
        @"destinationPath": destination, @"title": metadata[@"title"],
        @"artworkImported": @(artwork != nil), @"stagingRemoved": @YES, @"error": @""
    };
}

static void processMetadataBatch(NSDictionary *request, NSString *requestID) {
    NSArray *items = [request[@"items"] isKindOfClass:[NSArray class]] ? request[@"items"] : @[];
    NSMutableArray *results = [NSMutableArray arrayWithCapacity:items.count];
    for (id value in items) {
        @autoreleasepool {
            if (![value isKindOfClass:[NSDictionary class]]) {
                [results addObject:@{@"ok": @NO, @"error": @"Invalid metadata item"}];
                continue;
            }
            NSDictionary *item = value;
            NSString *source = item[@"sourcePath"];
            NSString *filename = [item[@"filename"] isKindOfClass:[NSString class]] ? item[@"filename"] : @"";
            if (!validSourcePath(source)) {
                [results addObject:@{@"filename": filename, @"ok": @NO, @"error": @"Invalid or missing source file"}];
                continue;
            }
            NSDictionary *metadata = metadataForAudioFile(source, item[@"title"]);
            [results addObject:@{
                @"filename": filename, @"ok": @YES,
                @"title": metadata[@"title"] ?: @"",
                @"artist": metadata[@"artist"] ?: @"",
                @"album": metadata[@"album"] ?: @""
            }];
        }
    }
    writeResponse(@{@"requestID": requestID, @"action": @"metadata-batch", @"ok": @YES, @"results": results});
}

static void processBatchImport(NSDictionary *request, NSString *requestID) {
    NSArray *items = [request[@"items"] isKindOfClass:[NSArray class]]
        ? request[@"items"] : @[];
    NSMutableArray *results = [NSMutableArray arrayWithCapacity:items.count];
    for (id item in items) {
        @autoreleasepool {
            if (![item isKindOfClass:[NSDictionary class]]) {
                [results addObject:@{@"filename": @"", @"ok": @NO,
                    @"error": @"Invalid batch item"}];
            } else {
                [results addObject:importResult(item)];
            }
        }
    }
    writeResponse(@{@"requestID": requestID, @"action": @"import-batch",
        @"ok": @YES, @"results": results});
}

static void processRequest(void) {
    @autoreleasepool {
        NSDictionary *request = [NSDictionary dictionaryWithContentsOfFile:RequestPath];
        NSString *requestID = [request[@"requestID"] isKindOfClass:[NSString class]] ? request[@"requestID"] : @"";
        if (![request isKindOfClass:[NSDictionary class]] || requestID.length == 0) {
            writeResponse(@{@"requestID": requestID, @"ok": @NO, @"error": @"Invalid request"});
            return;
        }
        NSString *action = [request[@"action"] isKindOfClass:[NSString class]]
            ? request[@"action"]
            : @"import";

        if ([action isEqualToString:@"import"]) {
            processImport(request, requestID);
        } else if ([action isEqualToString:@"import-batch"]) {
            processBatchImport(request, requestID);
        } else if ([action isEqualToString:@"metadata-batch"]) {
            processMetadataBatch(request, requestID);
        } else {
            writeResponse(@{
                @"requestID": requestID,
                @"action": action,
                @"ok": @NO,
                @"error": @"The Filza bridge supports imports only"
            });
        }
    }
}

static void requestReceived(CFNotificationCenterRef center, void *observer,
    CFStringRef name, const void *object, CFDictionaryRef userInfo) {
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{ processRequest(); });
}

%ctor {
    @autoreleasepool {
        if (NSClassFromString(@"TGMusicImporter") == Nil) return;
        CFNotificationCenterAddObserver(
            CFNotificationCenterGetDarwinNotifyCenter(), NULL, requestReceived,
            RequestNotification, NULL, CFNotificationSuspensionBehaviorDeliverImmediately
        );
    }
}
