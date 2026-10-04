local LrTasks = import 'LrTasks'
local LrLogger = import 'LrLogger'
local LrDialogs = import 'LrDialogs'
local LrPrefs = import 'LrPrefs'

local logger = LrLogger('AutoInstaExport')
logger:enable('logfile')
datetimeNow = os.date('%Y-%m-%d %H:%M:%S')
logger:info('Init.lua loaded at ' .. datetimeNow)

-- Default to enabled on first install; afterwards the toggle menu item persists this.
local prefs = LrPrefs.prefsForPlugin()
if prefs.autoExportEnabled == nil then
    prefs.autoExportEnabled = true
end

local ok, loadErr = pcall(function()
    local Config = require 'Config'
    local ExportTask = require 'ExportTask'

    -- local logger = LrLogger('AutoInstaExport')
    -- logger:enable('logfile')

    LrTasks.startAsyncTask(function()
        logger:info('AutoInstaExport background polling started')
        LrTasks.sleep(10) -- let catalog finish opening before the first pass
        while true do
            if prefs.autoExportEnabled then
                local passOk, err = LrTasks.pcall(ExportTask.runExportPass)
                if not passOk then
                    logger:error('Export pass failed: ' .. tostring(err))
                end
            end
            LrTasks.sleep(Config.pollIntervalSeconds)
        end
    end)
end)

if not ok then
    LrDialogs.message('AutoInstaExport failed to initialize', tostring(loadErr), 'critical')
end
