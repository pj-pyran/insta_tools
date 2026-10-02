local LrTasks = import 'LrTasks'
local LrLogger = import 'LrLogger'

local Config = require 'Config'
local ExportTask = require 'ExportTask'

local logger = LrLogger('AutoInstaExport')
logger:enable('logfile')

LrTasks.startAsyncTask(function()
    logger:info('AutoInstaExport background polling started')
    while true do
        local ok, err = LrTasks.pcall(ExportTask.runExportPass)
        if not ok then
            logger:error('Export pass failed: ' .. tostring(err))
        end
        LrTasks.sleep(Config.pollIntervalSeconds)
    end
end)
