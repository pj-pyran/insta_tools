local LrApplication = import 'LrApplication'
local LrTasks = import 'LrTasks'
local LrFileUtils = import 'LrFileUtils'
local LrPathUtils = import 'LrPathUtils'
local LrExportSession = import 'LrExportSession'
local LrLogger = import 'LrLogger'

local Config = require 'Config'

local logger = LrLogger('AutoInstaExport')
logger:enable('logfile')

local ExportTask = {}

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
    for _, kw in ipairs(photo:getRawMetadata('keywords')) do
        if kw == keyword then
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

-- Crops to Instagram's supported aspect ratio range, then resizes to final dims.
local function cropAndResizeForInstagram(path)
    local width, height = getImageDimensions(path)
    if not width or not height then
        logger:error('Could not read dimensions for ' .. path)
        return false
    end

    local ratio = width / height
    local cropWidth, cropHeight = width, height

    if ratio < Config.minAspectRatio then
        cropHeight = math.floor(width / Config.minAspectRatio)
    elseif ratio > Config.maxAspectRatio then
        cropWidth = math.floor(height * Config.maxAspectRatio)
    end

    if cropWidth ~= width or cropHeight ~= height then
        LrTasks.execute(
            string.format('sips -c %d %d %s', cropHeight, cropWidth, shellQuote(path))
        )
    end

    local finalRatio = cropWidth / cropHeight
    local finalWidth = math.min(Config.maxWidth, cropWidth)
    local finalHeight = math.floor(finalWidth / finalRatio)
    if finalHeight > Config.maxHeight then
        finalHeight = Config.maxHeight
        finalWidth = math.floor(finalHeight * finalRatio)
    end

    LrTasks.execute(
        string.format('sips -z %d %d %s', finalHeight, finalWidth, shellQuote(path))
    )
    return true
end

local function writeCaptionFile(path, photo)
    local f = io.open(path, 'w')
    if f then
        f:write(Config.captionText)
        f:close()
    end
end

function ExportTask.runExportPass()
    local catalog = LrApplication.activeCatalog()

    local forExportKeyword = findKeywordByName(catalog:getKeywords(), Config.forExportKeywordName)
    local autoExportedKeyword = catalog:withWriteAccessDo('AutoInstaExport: ensure keyword', function()
        return catalog:createKeyword(Config.autoExportedKeywordName, {}, false, nil, true)
    end)

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

    logger:info(string.format('Exporting %d photo(s) tagged "%s"', #candidates, Config.forExportKeywordName))

    LrFileUtils.createAllDirectories(Config.exportFolder)

    local exportSettings = {
        LR_export_destinationType = 'specificFolder',
        LR_export_destinationPathPrefix = Config.exportFolder,
        LR_export_useSubfolder = false,
        LR_format = 'JPEG',
        LR_jpeg_quality = Config.jpegQuality,
        LR_size_doConstrain = false,
        LR_collisionHandling = 'rename',
        LR_minimizeEmbeddedMetadata = false,
        LR_outputSharpeningOn = true,
        LR_outputSharpeningMedia = 'screen',
    }

    local exportSession = LrExportSession {
        photosToExport = candidates,
        exportSettings = exportSettings,
    }

    for _, rendition in exportSession:renditions() do
        local success, pathOrMessage = rendition:waitForRender()
        if success then
            local ok = cropAndResizeForInstagram(pathOrMessage)
            if ok then
                local captionPath = LrPathUtils.replaceExtension(pathOrMessage, 'txt')
                writeCaptionFile(captionPath, rendition.photo)

                catalog:withWriteAccessDo('AutoInstaExport: tag photo', function()
                    rendition.photo:addKeyword(autoExportedKeyword)
                end)

                logger:info('Exported ' .. pathOrMessage)
            else
                logger:error('Post-processing failed for ' .. pathOrMessage)
            end
        else
            logger:error('Export failed: ' .. tostring(pathOrMessage))
        end
    end
end

return ExportTask
