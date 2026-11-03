-- Defaults. Put personal overrides (e.g. exportFolder) in ConfigLocal.lua, which is gitignored.
local Config = {
    exportFolder = '/path/to/GoogleDrive/My Drive/_insta_auto',
    forExportKeywordName = 'for_insta',
    autoExportedKeywordName = 'auto_exported',
    captionText = '\n\nthe key to actually posting your work to IG? write some scripts to do it for you!',
    pollIntervalSeconds = 30,
    jpegQuality = 0.9,
    maxWidth = 1080,
    maxHeight = 1350,
    minAspectRatio = 0.8,  -- 4:5 portrait, Instagram's narrowest supported ratio
    maxAspectRatio = 1.91, -- widest supported landscape ratio
}

local ok, localConfig = pcall(require, 'ConfigLocal')
if ok and type(localConfig) == 'table' then
    for key, value in pairs(localConfig) do
        Config[key] = value
    end
end

return Config
