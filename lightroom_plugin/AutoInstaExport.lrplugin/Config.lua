-- Edit exportFolder if your Google Drive sync path differs.
return {
    exportFolder = '/Users/peter/Library/CloudStorage/GoogleDrive-petersargentgcse@gmail.com/My Drive/sync_folder/pictures/_photo/_insta_auto',
    forExportKeywordName = 'for_insta',
    autoExportedKeywordName = 'auto_exported',
    captionText = '\n\nthis was auto-uploaded by a script!',
    pollIntervalSeconds = 120,
    jpegQuality = 0.9,
    maxWidth = 1080,
    maxHeight = 1350,
    minAspectRatio = 0.8,  -- 4:5 portrait, Instagram's narrowest supported ratio
    maxAspectRatio = 1.91, -- widest supported landscape ratio
}
