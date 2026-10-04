local LrPrefs = import 'LrPrefs'
local LrDialogs = import 'LrDialogs'

local prefs = LrPrefs.prefsForPlugin()
prefs.autoExportEnabled = not prefs.autoExportEnabled

LrDialogs.showBezel(
    prefs.autoExportEnabled and 'Auto Insta Export: auto-export ON' or 'Auto Insta Export: auto-export OFF'
)
