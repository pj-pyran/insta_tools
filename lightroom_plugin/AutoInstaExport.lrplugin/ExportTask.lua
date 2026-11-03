local LrApplication = import 'LrApplication'
local LrTasks = import 'LrTasks'
local LrFileUtils = import 'LrFileUtils'
local LrPathUtils = import 'LrPathUtils'
local LrExportSession = import 'LrExportSession'
local LrLogger = import 'LrLogger'
local LrProgressScope = import 'LrProgressScope'
local LrFunctionContext = import 'LrFunctionContext'
local LrDate = import 'LrDate'

local Config = require 'Config'

local logger = LrLogger('AutoInstaExport')
logger:enable('logfile')
datetimeNow = os.date('%Y-%m-%d %H:%M:%S')
local ExportTask = {}

-- Guards against the background poll loop and a manual trigger running
-- concurrently, which causes catalogue write-access conflicts.
local isRunning = false

local function shellQuote(value)
    return "'" .. tostring(value):gsub("'", "'\\''") .. "'"
end

-- Keywords can be nested, so finding one by name requires walking the tree.
local function findKeywordByName(keywords, name)
    for _, keyword in ipairs(keywords) do
        if keyword:getName() == name then
            return keyword
        end
        local found = findKeywordByName(keyword:getChildren(), name)
        if found then
            return found
        end
    end
    return nil
end

local function photoHasKeyword(photo, keyword)
    -- Compare by name, not object identity: getRawMetadata('keywords') can
    -- return freshly-wrapped keyword objects that fail reference equality
    -- even when they represent the same catalogue keyword.
    local targetName = keyword:getName()
    for _, kw in ipairs(photo:getRawMetadata('keywords')) do
        if kw:getName() == targetName then
            return true
        end
    end
    return false
end

local function getImageDimensions(path)
    local tmpOut = LrPathUtils.child(LrPathUtils.parent(path), '.aie_dims.txt')
    LrTasks.execute(
        string.format('sips -g pixelWidth -g pixelHeight %s > %s 2>&1',
            shellQuote(path), shellQuote(tmpOut))
    )
    local width, height
    local f = io.open(tmpOut, 'r')
    if f then
        for line in f:lines() do
            local w = line:match('pixelWidth:%s*(%d+)')
            local h = line:match('pixelHeight:%s*(%d+)')
            if w then width = tonumber(w) end
            if h then height = tonumber(h) end
        end
        f:close()
        LrFileUtils.delete(tmpOut)
    end
    return width, height
end

-- formatOptions takes a 0-100 integer; Config.jpegQuality is a 0-1 fraction
-- (matching Lightroom's LR_jpeg_quality convention), so it's scaled here.
local sipsQuality = math.floor(Config.jpegQuality * 100 + 0.5)

-- Only crops when outside Instagram's supported range, and only by the
-- minimum amount needed to reach the nearest valid ratio (preserves the
-- original artistic crop otherwise). Only resizes when actually oversized.
-- Every sips re-encode step is given an explicit quality so Config.jpegQuality
-- isn't silently overridden by sips's own default.
local function cropAndResizeForInstagram(path)
    local width, height = getImageDimensions(path)
    if not width or not height then
        logger:error('Could not read dimensions for ' .. path)
        return false
    end

    logger:info(string.format('Source dimensions %dx%d: %s', width, height, path))
    local ratio = width / height
    local cropWidth, cropHeight = width, height

    if ratio < Config.minAspectRatio then
        cropHeight = math.floor(width / Config.minAspectRatio)
    elseif ratio > Config.maxAspectRatio then
        cropWidth = math.floor(height * Config.maxAspectRatio)
    end

    if cropWidth ~= width or cropHeight ~= height then
        LrTasks.execute(
            string.format('sips -c %d %d -s formatOptions %d %s',
                cropHeight, cropWidth, sipsQuality, shellQuote(path))
        )
    end

    local finalRatio = cropWidth / cropHeight
    local finalWidth = math.min(Config.maxWidth, cropWidth)
    local finalHeight = math.floor(finalWidth / finalRatio)
    if finalHeight > Config.maxHeight then
        finalHeight = Config.maxHeight
        finalWidth = math.floor(finalHeight * finalRatio)
    end

    if finalWidth < cropWidth or finalHeight < cropHeight then
        LrTasks.execute(
            string.format('sips -z %d %d -s formatOptions %d %s',
                finalHeight, finalWidth, sipsQuality, shellQuote(path))
        )
    end

    return true
end

local function writeCaptionFile(path, photo)
    local f = io.open(path, 'w')
    if f then
        f:write('\n\nthe key to actually posting your work to IG? write some scripts to do it for you!')
        f:close()
    end
end

-- Capture date as YYYY-MM-DD, or nil when the photo has none. Capture times
-- are stored as local time-of-day, so format them as GMT to avoid a shift.
local function captureDate(photo)
    local t = photo:getRawMetadata('dateTimeOriginal')
    if not t then return nil end
    return LrDate.timeToUserFormat(t, '%Y-%m-%d', true)
end

local function captureTime(photo)
    return photo:getRawMetadata('dateTimeOriginal') or math.huge
end

-- Each planned post date is a subfolder of the export folder, named
-- YYYY-MM-DD; everything in it is posted together as one carousel. Photos
-- default to their capture date; move folders/files in Drive to regroup or
-- reschedule. Photos with no capture date go to "undated" (rename it to a
-- date to schedule it).
local function postFolderName(photo)
    return captureDate(photo) or 'undated'
end

-- File name (no extension) within a post folder: <seq>-<original name>.
-- Seq continues from what's already in the folder so order follows shooting
-- order across passes.
local function queueName(photo, folder, seqByFolder)
    if not seqByFolder[folder] then
        local count = 0
        for path in LrFileUtils.files(folder) do
            if LrPathUtils.extension(path):lower() == 'jpg' then
                count = count + 1
            end
        end
        seqByFolder[folder] = count
    end
    seqByFolder[folder] = seqByFolder[folder] + 1
    local original = LrPathUtils.removeExtension(LrPathUtils.leafName(photo:getRawMetadata('path')))
    return string.format('%03d-%s', seqByFolder[folder], original)
end

function ExportTask.runExportPass()
    if isRunning then
        logger:info('Skipping pass: another export pass is already running')
        return
    end
    isRunning = true
    local ok, err = LrTasks.pcall(ExportTask.runExportPassInner)
    isRunning = false
    if not ok then
        error(err, 0)
    end
end

function ExportTask.runExportPassInner()
    local catalog = LrApplication.activeCatalog()

    local forExportKeyword = findKeywordByName(catalog:getKeywords(), Config.forExportKeywordName)

    -- withWriteAccessDo doesn't return the inner function's result, so the
    -- created/existing keyword must be captured via an upvalue instead.
    -- createKeyword(name, synonyms, includeOnExport, parent, returnExisting)
    local autoExportedKeyword
    catalog:withWriteAccessDo('AutoInstaExport: ensure keyword', function()
        autoExportedKeyword = catalog:createKeyword(Config.autoExportedKeywordName, {}, false, nil, true)
    end)

    if not autoExportedKeyword then
        error('Failed to create or find keyword "' .. Config.autoExportedKeywordName .. '"')
    end

    if not forExportKeyword then
        logger:info('No "' .. Config.forExportKeywordName .. '" keyword found in catalog; nothing to do')
        return
    end

    local candidates = {}
    for _, photo in ipairs(forExportKeyword:getPhotos()) do
        if not photoHasKeyword(photo, autoExportedKeyword) then
            table.insert(candidates, photo)
        end
    end

    if #candidates == 0 then
        logger:info('No new photos tagged "' .. Config.forExportKeywordName .. '" to export')
        return
    end

    -- Shooting order, so sequence numbers within a day follow it.
    -- Times are read up front: metadata calls can yield, which isn't allowed
    -- inside a table.sort comparator.
    local times = {}
    for _, photo in ipairs(candidates) do
        times[photo] = captureTime(photo)
    end
    table.sort(candidates, function(a, b) return times[a] < times[b] end)
    local seqByFolder = {}

    logger:info(string.format('Exporting %d photo(s) tagged "%s"', #candidates, Config.forExportKeywordName))
    
    local exportSettings = {
        LR_export_destinationType = 'specificFolder',
        LR_export_useSubfolder = false,
        LR_format = 'JPEG',
        LR_jpeg_quality = Config.jpegQuality,
        LR_size_doConstrain = false,
        LR_collisionHandling = 'rename',
        LR_minimizeEmbeddedMetadata = false,
        LR_outputSharpeningOn = true,
        LR_outputSharpeningMedia = 'screen',
    }

    -- One session per photo: each photo is fully finished (rendered, resized,
    -- captioned, tagged) before the next starts, so an interruption never
    -- leaves exported photos untagged. Tagging happens between sessions, when
    -- nothing is rendering, which avoids the SDK assert.
    LrFunctionContext.callWithContext('AutoInstaExport_progress', function(context)
        local progressScope = LrProgressScope {
            title = 'Auto Insta Export',
            functionContext = context,
        }

        for index, photo in ipairs(candidates) do
            if progressScope:isCanceled() then
                break
            end
            progressScope:setCaption(LrPathUtils.leafName(photo:getRawMetadata('path')))
            progressScope:setPortionComplete(index - 1, #candidates)

            local postFolder = LrPathUtils.child(Config.exportFolder, postFolderName(photo))
            LrFileUtils.createAllDirectories(postFolder)
            exportSettings.LR_export_destinationPathPrefix = postFolder

            local exportSession = LrExportSession {
                photosToExport = { photo },
                exportSettings = exportSettings,
            }

            for _, rendition in exportSession:renditions() do
                local success, pathOrMessage = rendition:waitForRender()
                if not success then
                    logger:error('Export failed: ' .. tostring(pathOrMessage))
                else
                    logger:info('Rendered ' .. pathOrMessage)
                    local newPath = LrPathUtils.child(
                        LrPathUtils.parent(pathOrMessage),
                        LrPathUtils.addExtension(queueName(photo, postFolder, seqByFolder), 'jpg')
                    )
                    if LrFileUtils.move(pathOrMessage, newPath) then
                        pathOrMessage = newPath
                    else
                        logger:error('Could not rename ' .. pathOrMessage .. ' to ' .. newPath)
                    end
                    if cropAndResizeForInstagram(pathOrMessage) then
                        writeCaptionFile(LrPathUtils.replaceExtension(pathOrMessage, 'txt'), photo)
                        catalog:withWriteAccessDo('AutoInstaExport: tag photo', function()
                            photo:addKeyword(autoExportedKeyword)
                        end)
                        logger:info('Exported ' .. pathOrMessage)
                    else
                        logger:error('Post-processing failed for ' .. pathOrMessage)
                    end
                end
            end
        end

        progressScope:done()
    end)
end

return ExportTask
