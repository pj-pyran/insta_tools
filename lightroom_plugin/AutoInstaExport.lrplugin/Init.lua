local LrTasks = import 'LrTasks'
local LrLogger = import 'LrLogger'
local LrDialogs = import 'LrDialogs'

local logger = LrLogger('AutoInstaExport')
logger:enable('logfile')
datetimeNow = os.date('%Y-%m-%d %H:%M:%S')
logger:info('Init.lua loaded at ' .. datetimeNow)

local ok, loadErr = pcall(function()
    local Config = require 'Config'
    local ExportTask = require 'ExportTask'

    -- local logger = LrLogger('AutoInstaExport')
    -- logger:enable('logfile')

    LrTasks.startAsyncTask(function()
        logger:info('AutoInstaExport background polling started')
        LrTasks.sleep(10) -- let catalog finish opening before the first pass
        while true do
            local passOk, err = LrTasks.pcall(ExportTask.runExportPass)
            if not passOk then
                logger:error('Export pass failed: ' .. tostring(err))
            end
            LrTasks.sleep(Config.pollIntervalSeconds)
        end
    end)
end)

if not ok then
    LrDialogs.message('AutoInstaExport failed to initialize', tostring(loadErr), 'critical')
end
